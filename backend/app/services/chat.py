import asyncio
import json
import re
import uuid
from typing import AsyncGenerator

import structlog

from app.database import get_connection
from app.config import settings
from app.utils.llm import chat_completion, stream_chat_completion, LLM_TOOLS, execute_tool, get_date_prefix
from app.utils.token_counter import count_messages_tokens
from app.prompts.core_system import CORE_SYSTEM_PROMPT

logger = structlog.get_logger()


async def create_session() -> str:
    """创建新会话，返回 session_id"""
    session_id = uuid.uuid4().hex
    async with get_connection() as db:
        await db.execute(
            "INSERT INTO messages (id, role, content, mode, session_id) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, "system", "新会话已创建", "system", session_id),
        )
        await db.commit()
    return session_id


async def list_sessions() -> list[dict]:
    """获取会话列表，按最后消息时间倒序"""
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT m.session_id,
                   MAX(CASE WHEN m.mode = 'system' THEN m.content END) as title,
                   MAX(m.created_at) as last_message_at,
                   COUNT(CASE WHEN m.mode != 'system' THEN 1 END) as message_count
            FROM messages m
            GROUP BY m.session_id
            HAVING message_count > 0
            ORDER BY last_message_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_session_messages(session_id: str, limit: int = 50) -> list[dict]:
    """获取会话消息历史"""
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM messages WHERE session_id = ? AND mode != 'system' ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_session(session_id: str) -> None:
    """删除会话及其所有消息"""
    async with get_connection() as db:
        await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await db.commit()


async def rename_session(session_id: str, title: str) -> None:
    title = title.strip()[:100]
    if not title:
        return
    async with get_connection() as db:
        await db.execute(
            "UPDATE messages SET content = ? WHERE session_id = ? AND mode = 'system'",
            (title, session_id),
        )
        await db.commit()


async def save_message(role: str, content: str, session_id: str, mode: str = "chat") -> str:
    """保存消息到数据库"""
    msg_id = uuid.uuid4().hex
    async with get_connection() as db:
        await db.execute(
            "INSERT INTO messages (id, role, content, mode, session_id) VALUES (?, ?, ?, ?, ?)",
            (msg_id, role, content, mode, session_id),
        )
        await db.commit()
    return msg_id


async def _generate_session_title(session_id: str, first_message: str) -> None:
    """为会话生成标题"""
    from app.utils.llm import chat_completion
    title = await chat_completion(
        messages=[{"role": "user", "content": f"为以下对话生成一个简短的标题（10字以内，不要标点）：\n{first_message}"}],
        temperature=0.3,
        max_tokens=30,
        purpose="会话标题生成",
    )
    title = title.strip().strip('"').strip("'")[:20]
    async with get_connection() as db:
        await db.execute(
            "UPDATE messages SET content = ? WHERE session_id = ? AND mode = 'system'",
            (title, session_id)
        )
        await db.commit()


async def _detect_context(user_message: str, history: list[dict]) -> dict:
    """使用 mini 模型检测对话情境和用户意图"""
    recent_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in history[-6:]
    )
    prompt = (
        "根据以下对话内容，判断：\n"
        "1. 对话情境类别（只输出类别名称）\n"
        "2. 用户意图是「分享」还是「分析」\n"
        "   - 分享：用户在轻松地讲述自己的经历、成就、日常，语气积极或中性\n"
        "   - 分析：用户在寻求深入分析、问「为什么」、表达困惑、请求帮助理解自己\n\n"
        "可选情境类别：default, family, work, decision, social, media\n"
        "意图类别：share, analyze\n\n"
        f"对话：\n{recent_text}\n用户最新消息：{user_message}\n\n"
        '请用JSON格式输出：{"context": "类别", "intent": "share或analyze"}'
    )
    try:
        result = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=settings.llm.chat_mini_model,
            temperature=0.1,
            max_tokens=64,
            purpose="意图识别",
        )
        # Parse JSON response
        import re
        json_match = re.search(r'\{[^}]+\}', result)
        if json_match:
            parsed = json.loads(json_match.group())
            context_type = parsed.get("context", "default").strip().lower()
            user_intent = parsed.get("intent", "share").strip().lower()
        else:
            context_type = result.strip().lower()
            user_intent = "share"

        valid_types = {"default", "family", "work", "decision", "social", "media"}
        if context_type not in valid_types:
            context_type = "default"
        if user_intent not in {"share", "analyze"}:
            user_intent = "share"
    except Exception:
        logger.exception("情境检测失败，使用默认情境")
        context_type = "default"
        user_intent = "share"

    return {"primary_context": context_type, "user_intent": user_intent}


async def _empty_rag_result() -> dict:
    """检索模式未启用 RAG 时返回的空结果（保持结构兼容）"""
    return {
        "timeline_context": "",
        "diary_context": "",
        "sources": [],
    }


async def _empty_entity_result() -> dict:
    """检索模式未启用实体图搜索时返回的空结果"""
    return {"hits": [], "neighbors": [], "context_text": ""}


async def chat_stream(
    session_id: str,
    user_message: str,
    retrieval_mode: str = "both",
    enable_web_search: bool = False,
) -> AsyncGenerator[str, None]:
    """SSE 流式对话（集成新 RAG + 实体图搜索 + 三层记忆）

    retrieval_mode: "rag" 仅 RAG 检索 | "entity" 仅实体图搜索 | "both" 两者都启用（默认）
    enable_web_search: 是否启用联网搜索工具（默认关闭）
    """
    # 根据开关决定暴露给模型的工具列表
    if enable_web_search:
        active_tools = LLM_TOOLS
        web_search_hint = "你可以使用联网搜索工具来查找实时信息。当用户询问最新新闻、实时数据、具体事实等问题时，主动调用 web_search 工具搜索。"
    else:
        # 不传 tools 参数，彻底阻止模型调用工具
        active_tools = None
        web_search_hint = "你当前没有联网搜索功能，无法搜索互联网。绝对不要假装搜索或编造搜索结果。如果你不知道某个事实，直接说不知道，不要编造信息或假装已搜索。"
    # 1. 保存用户消息（原始消息）
    await save_message("user", user_message, session_id)

    # 1b. 动态上下文注入已移除（对话不做任何记忆/事实提取）
    modified_message = user_message

    # 2. 获取会话历史
    history = await get_session_messages(session_id)

    # 3-7. 并行执行预处理步骤（情境检测、RAG检索、实体图搜索、中期记忆、快照、变化检测）
    from app.services.rag import hybrid_rag
    from app.services.graph_search import entity_search
    from app.services.memory import memory_manager
    from app.services.snapshot import get_or_build_snapshot_layers
    from app.services.change_detector import get_unpresented_changes, mark_change_presented
    from app.utils.embedding import embed_texts

    # 根据 retrieval_mode 决定执行哪些检索
    use_rag = retrieval_mode in ("rag", "both")
    use_entity = retrieval_mode in ("entity", "both")

    # 提前计算 query embedding，共享给 RAG 和 entity_search（避免重复调用 embedding API）
    query_vector = None
    if use_rag or use_entity:
        try:
            query_vector = (await embed_texts([user_message]))[0]
        except Exception:
            logger.exception("query_embedding_failed")
            query_vector = None

    # 并行执行：情境检测、RAG检索（可选）、实体图搜索（可选）、中期记忆、双层快照、变化检测
    tasks = []
    task_names = []

    # 情境检测（user_intent 仅在构建 prompt 时使用，可并行）
    tasks.append(asyncio.create_task(_detect_context(user_message, history)))
    task_names.append("context")

    if use_rag:
        tasks.append(asyncio.create_task(hybrid_rag.retrieve(
            query=user_message,
            context={},  # context 由并行任务填充，此处传空（rag 检索不依赖 context）
            query_vector=query_vector,
        )))
        task_names.append("rag")
    else:
        tasks.append(asyncio.create_task(_empty_rag_result()))
        task_names.append("rag")

    if use_entity:
        tasks.append(asyncio.create_task(entity_search(user_message, query_vector=query_vector)))
        task_names.append("entity")
    else:
        tasks.append(asyncio.create_task(_empty_entity_result()))
        task_names.append("entity")

    tasks.append(asyncio.create_task(memory_manager.get_mid_term_memory(session_id)))
    task_names.append("mid_term")

    tasks.append(asyncio.create_task(get_or_build_snapshot_layers()))
    task_names.append("snapshot")

    tasks.append(asyncio.create_task(get_unpresented_changes()))
    task_names.append("changes")

    # 等待所有任务完成
    results = await asyncio.gather(*tasks)
    context = results[0]
    rag_result = results[1]
    entity_result = results[2]
    mid_term_summary = results[3]
    snapshot_layers = results[4]
    unpresented_changes = results[5]

    user_intent = context.get("user_intent", "share")

    # 5a. Determine retrieval source for observability
    retrieval_source = "cache"
    rag_sources = rag_result.get("sources", [])
    entity_hits = entity_result.get("hits", [])
    if rag_sources or entity_hits:
        # 优先级：实体命中 > 时间线 > 日记
        if entity_hits:
            retrieval_source = "entity_graph"
        elif rag_sources:
            source_counts = {}
            for s in rag_sources:
                stype = s.get("type", "unknown")
                source_counts[stype] = source_counts.get(stype, 0) + 1
            if source_counts:
                if source_counts.get("timeline", 0) > 0:
                    retrieval_source = "timeline_rag"
                elif source_counts.get("diary", 0) > 0:
                    retrieval_source = "diary_rag"
                else:
                    retrieval_source = "rag"

    # 5b. RAG + 实体重排序融合：当 retrieval_mode == "both" 时，合并候选并重排
    if retrieval_mode == "both" and (entity_hits or rag_result.get("diary_context")):
        try:
            from app.services.reranker import rerank as do_rerank

            candidates: list[dict] = []
            # 实体命中
            for h in entity_hits:
                candidates.append({
                    "slug": h.get("slug", ""),
                    "snippet": (h.get("compiled_truth", "") or "")[:300],
                    "_source_type": "entity_hit",
                    "_raw": h,
                })
            # 实体邻居
            for n in entity_result.get("neighbors", []):
                candidates.append({
                    "slug": n.get("slug", ""),
                    "snippet": (n.get("compiled_truth", "") or "")[:300],
                    "_source_type": "entity_neighbor",
                    "_raw": n,
                })
            # RAG 日记原文片段
            for s in rag_sources:
                if s.get("type") == "diary":
                    candidates.append({
                        "source_id": s.get("source_id", ""),
                        "snippet": s.get("content_preview", ""),
                        "_source_type": "diary",
                        "_raw": s,
                    })

            if candidates:
                reranked = await do_rerank(user_message, candidates, top_n=15)
                # 按重排结果重构 entity_ctx
                rerank_lines: list[str] = []
                hit_lines: list[str] = []
                neighbor_lines: list[str] = []
                diary_lines: list[str] = []

                for c in reranked:
                    raw = c.get("_raw", {})
                    stype = c.get("_source_type", "")
                    score = c.get("_rerank_score", 0)
                    if stype == "entity_hit":
                        truth = (raw.get("compiled_truth", "") or "")[:300]
                        if len(raw.get("compiled_truth", "") or "") > 300:
                            truth += "..."
                        hit_lines.append(
                            f"- [{raw.get('type', '')}] {raw.get('title', '')}：{truth}"
                        )
                    elif stype == "entity_neighbor":
                        truth = (raw.get("compiled_truth", "") or "")[:300]
                        if len(raw.get("compiled_truth", "") or "") > 300:
                            truth += "..."
                        neighbor_lines.append(
                            f"- [{raw.get('type', '')}] {raw.get('title', '')}"
                            f"（{raw.get('depth', 1)}跳）：{truth}"
                        )
                    elif stype == "diary":
                        diary_lines.append(
                            f"- [{raw.get('source_date', '')}] {raw.get('content_preview', '')}"
                        )

                if hit_lines:
                    rerank_lines.append("命中的实体：")
                    rerank_lines.extend(hit_lines)
                if neighbor_lines:
                    if rerank_lines:
                        rerank_lines.append("")
                    rerank_lines.append("相关实体（图谱搜索）：")
                    rerank_lines.extend(neighbor_lines)
                if diary_lines:
                    if rerank_lines:
                        rerank_lines.append("")
                    rerank_lines.append("相关日记原文：")
                    rerank_lines.extend(diary_lines)

                entity_result["context_text"] = "\n".join(rerank_lines)
                logger.info("rerank_completed", candidate_count=len(candidates), reranked_count=len(reranked))
        except Exception:
            logger.exception("重排序融合失败，使用原始结果")

    # 5c. RAG 模式下：对时间线命中事件重排，重排后读取 source_id 对应日记原文
    if retrieval_mode == "rag" and rag_result.get("timeline_context"):
        try:
            from app.services.reranker import rerank as do_rerank
            from app.services.diary import get_diary

            # 收集命中的时间线事件作为重排候选
            timeline_hit_sources = [s for s in rag_sources if s.get("type") == "timeline" and s.get("is_hit")]
            candidates = []
            for s in timeline_hit_sources:
                candidates.append({
                    "id": s.get("id", ""),
                    "snippet": s.get("summary", ""),
                    "timestamp": s.get("timestamp", ""),
                    "source_type": s.get("source_type", ""),
                    "source_id": s.get("source_id", ""),
                    "_source_type": "timeline_hit",
                    "_raw": s,
                })

            if candidates:
                # 重排，取 top 5（避免读取太多日记原文）
                reranked = await do_rerank(user_message, candidates, top_n=5)

                # 对重排后的命中事件，读取 source_id 对应的日记原文（仅 diary 来源）
                diary_lines: list[str] = []
                seen_diary_ids: set = set()
                for c in reranked:
                    source_type = c.get("source_type", "")
                    source_id = c.get("source_id", "")
                    if source_type == "diary" and source_id and source_id not in seen_diary_ids:
                        seen_diary_ids.add(source_id)
                        try:
                            diary = await get_diary(source_id)
                            if diary and diary.content:
                                # 截取前 800 字，避免过长
                                diary_content = diary.content[:800]
                                if len(diary.content) > 800:
                                    diary_content += "..."
                                diary_lines.append(f"- [{diary.date}] {diary_content}")
                        except Exception:
                            logger.warning("read_diary_failed", source_id=source_id)

                # 构建 entity_ctx：时间线摘要 + 重排后读取的日记原文
                entity_lines: list[str] = []
                entity_lines.append("相关时间线事件：")
                entity_lines.append(rag_result["timeline_context"])

                if diary_lines:
                    entity_lines.append("")
                    entity_lines.append("相关日记原文（基于时间线命中重排）：")
                    entity_lines.extend(diary_lines)

                entity_result["context_text"] = "\n".join(entity_lines)
                logger.info("rag_timeline_rerank_completed",
                           candidate_count=len(candidates),
                           reranked_count=len(reranked),
                           diary_read=len(diary_lines))
        except Exception:
            logger.exception("RAG 时间线重排失败，使用原始结果")
            # 失败时回退：时间线上下文直接注入 entity_ctx
            if rag_result.get("timeline_context"):
                entity_result["context_text"] = f"相关时间线事件：\n{rag_result['timeline_context']}"

    # 5d. 媒体知识检索已移除（对话不写入知识库/实体）

    # 7. 构建 messages 列表 — 双层快照 + 动态区，优化 KV Cache 命中
    messages = []

    # ── 冻结区（核心层）：会话内不变，命中 KV Cache ──
    # 核心层 = 长期画像 + 高频实体，放在 System Prompt 最前面
    # 画像由 snapshot 快照层提供，RAG 不再检索画像
    core_profile = snapshot_layers.core_text or "暂无画像数据"

    # ── 缓存区（情境层）：会话内缓存不变 ──
    # 情境层 = 月/周画像 + 按类型实体
    context_profile = snapshot_layers.context_text or ""

    # ── 动态区：每次对话可能变化 ──
    entity_ctx = entity_result.get("context_text", "") or "暂无实体数据"

    # 将中期记忆摘要注入变化提醒区域
    change_ids_to_mark = [c["id"] for c in unpresented_changes]

    change_reminders = ""
    if unpresented_changes:
        change_lines = []
        for change in unpresented_changes:
            change_lines.append(f"- [{change['type']}] {change['description']}")
        change_reminders = "画像变化提醒：\n" + "\n".join(change_lines)

    if mid_term_summary:
        if change_reminders:
            change_reminders += "\n\n"
        change_reminders += f"近期对话摘要：{mid_term_summary}"
    # 时间线上下文注入变化提醒区域（RAG 模式下时间线已注入 entity_ctx，不再重复）
    if rag_result.get("timeline_context") and retrieval_mode != "rag":
        if change_reminders:
            change_reminders += "\n\n"
        change_reminders += f"近期时间线：\n{rag_result['timeline_context']}"
    # both 模式下日记原文已通过重排序融入 entity_ctx；entity 模式无 RAG 检索
    # RAG 模式下日记原文已通过时间线重排读取融入 entity_ctx
    # 仅当 diary_context 存在且未被处理时，注入变化提醒区域
    if rag_result.get("diary_context") and retrieval_mode == "rag":
        # RAG 模式下，日记原文片段（向量检索的）作为补充注入变化提醒
        if change_reminders:
            change_reminders += "\n\n"
        change_reminders += f"相关日记片段：\n{rag_result['diary_context']}"

    # 构建 System Prompt：[冻结区核心层] + [缓存区情境层] + [动态区]
    # 核心层放在 profile_context 位置（System Prompt 最前面的画像区域）
    # 情境层追加在 profile_context 之后
    profile_context_full = core_profile
    if context_profile:
        profile_context_full += "\n\n" + context_profile

    system_content = get_date_prefix() + CORE_SYSTEM_PROMPT.format(
        profile_context=profile_context_full,
        entity_context=entity_ctx,
        change_reminders=change_reminders,
        user_intent="用户在轻松分享经历" if user_intent == "share" else "用户在寻求深度分析",
    ) + "\n\n" + web_search_hint
    messages.append({"role": "system", "content": system_content})

    # 添加历史消息（排除系统消息）
    for msg in history:
        if msg["mode"] != "system":
            messages.append({"role": msg["role"], "content": msg["content"]})

    # 7b. 动态上下文注入：将最后一条用户消息替换为含动态上下文的版本
    if modified_message != user_message:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages[i]["content"] = modified_message
                break

    # 8. Token 预算控制
    total_tokens = count_messages_tokens(messages)
    max_context_tokens = settings.llm.max_tokens * 8

    if total_tokens > max_context_tokens:
        while len(messages) > 2 and count_messages_tokens(messages) > max_context_tokens:
            messages.pop(1)

    # 9. 调用 LLM（流式输出 + 工具调用支持）
    # Send retrieval_source event first
    yield f"data: {json.dumps({'retrieval_source': retrieval_source}, ensure_ascii=False)}\n\n"

    full_response = ""
    max_tool_rounds = 3  # 最多3轮工具调用，防止无限循环

    from app.utils.llm import get_llm_client as _get_llm_client, _log_llm_call, stream_chat_completion
    import asyncio as _asyncio

    client = _get_llm_client()
    use_model = settings.llm.chat_model

    for tool_round in range(max_tool_rounds):
        # 第一轮：先尝试流式调用（无 tools），如果 LLM 需要调用工具则回退到非流式
        if tool_round == 0:
            # 使用流式调用以降低首 token 延迟
            start_time = _asyncio.get_event_loop().time()
            collected_content = ""
            has_tool_call = False

            try:
                create_kwargs = dict(
                    model=use_model,
                    messages=messages,
                    temperature=settings.llm.temperature,
                    max_tokens=settings.llm.max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                if active_tools:
                    create_kwargs["tools"] = active_tools
                stream = await client.chat.completions.create(**create_kwargs)

                tool_calls_data = {}  # index -> {id, name, arguments}
                async for chunk in stream:
                    if not chunk.choices:
                        # Usage-only chunk
                        if hasattr(chunk, 'usage') and chunk.usage:
                            _log_llm_call("对话回复(流式)", _asyncio.get_event_loop().time() - start_time, chunk.usage.total_tokens, use_model)
                        continue

                    delta = chunk.choices[0].delta

                    # 处理工具调用
                    if delta.tool_calls:
                        has_tool_call = True
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_data:
                                tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.id:
                                tool_calls_data[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_data[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls_data[idx]["arguments"] += tc.function.arguments

                    # 处理文本内容
                    if delta.content:
                        collected_content += delta.content
                        # 过滤 [CORRECTION] 标记
                        display_chunk = re.sub(r'\[CORRECTION\].+?\[/CORRECTION\]', '', delta.content)
                        if display_chunk:
                            yield f"data: {json.dumps({'content': display_chunk}, ensure_ascii=False)}\n\n"

                    # 检查 finish_reason
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
                        break

                elapsed = _asyncio.get_event_loop().time() - start_time

            except Exception as e:
                logger.exception("流式调用失败，回退到非流式", error=str(e))
                has_tool_call = False
                collected_content = ""

            if has_tool_call and tool_calls_data:
                # LLM 请求了工具调用，处理工具调用
                # 先输出已收集的文字内容
                if collected_content:
                    full_response += collected_content

                # 构造 assistant 消息
                assistant_msg_dict = {
                    "role": "assistant",
                    "content": collected_content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_calls_data.values()
                    ],
                }
                messages.append(assistant_msg_dict)

                for tc in tool_calls_data.values():
                    tool_name = tc["name"]
                    try:
                        tool_args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    # 执行工具
                    tool_result = await execute_tool(tool_name, tool_args)

                    # 将工具结果加入 messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

                    yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args, 'result': json.loads(tool_result)}}, ensure_ascii=False)}\n\n"

                # 继续下一轮，让模型根据工具结果生成回复
                continue

            else:
                # 无工具调用，直接输出
                content = collected_content
                display_content = re.sub(r'\[CORRECTION\].+?\[/CORRECTION\]', '', content)
                full_response += content

                # 检查截断（流式模式下无法直接判断，检查内容是否突然结束）
                if content and not content.rstrip().endswith(('。', '！', '？', '」', '）', ')', '"', "'", '：', '…')):
                    # 可能被截断，但不一定，保守处理
                    pass

                break

        else:
            # 工具调用后的后续轮次，使用非流式（需要判断是否还有工具调用）
            start_time = _asyncio.get_event_loop().time()
            total_tokens = None

            create_kwargs = dict(
                model=use_model,
                messages=messages,
                temperature=settings.llm.temperature,
                max_tokens=settings.llm.max_tokens,
            )
            if active_tools:
                create_kwargs["tools"] = active_tools
            api_response = await client.chat.completions.create(**create_kwargs)

            if api_response.usage and api_response.usage.total_tokens:
                total_tokens = api_response.usage.total_tokens

            elapsed = _asyncio.get_event_loop().time() - start_time
            _log_llm_call("对话回复(工具轮)", elapsed, total_tokens, use_model)

            choice = api_response.choices[0]
            assistant_msg = choice.message

            # 无工具调用，直接输出
            if not assistant_msg.tool_calls:
                content = assistant_msg.content or ""
                display_content = re.sub(r'\[CORRECTION\].+?\[/CORRECTION\]', '', content)
                full_response += content
                if display_content.strip():
                    yield f"data: {json.dumps({'content': display_content}, ensure_ascii=False)}\n\n"

                # 检查截断
                finish_reason = choice.finish_reason
                if finish_reason == "length":
                    truncation_hint = "（回复因长度限制被截断，你可以继续追问）"
                    full_response += truncation_hint
                    yield f"data: {json.dumps({'content': truncation_hint, 'truncated': True}, ensure_ascii=False)}\n\n"
                    logger.warning("回复被截断", session_id=session_id, finish_reason=finish_reason)

                break

            # 还有工具调用
            if assistant_msg.content:
                full_response += assistant_msg.content
                yield f"data: {json.dumps({'content': assistant_msg.content}, ensure_ascii=False)}\n\n"

            messages.append(assistant_msg.model_dump())

            for tool_call in assistant_msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                tool_result = await execute_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

                yield f"data: {json.dumps({'tool_call': {'name': tool_name, 'args': tool_args, 'result': json.loads(tool_result)}}, ensure_ascii=False)}\n\n"

    # 10. 保存助手回复
    await save_message("assistant", full_response, session_id)

    # 10b. 检测回复中是否引用了画像数据，发送确认提示
    has_data_reference = bool(re.search(r'\d+[\.\d]*\s*(公里|千米|次|天|周|月|元|块|杯|份|小时|分钟)', full_response))
    if has_data_reference:
        yield f"data: {json.dumps({'data_confirmation': True}, ensure_ascii=False)}\n\n"

    # 10c. 检测回复中是否包含纠正标记
    correction_match = re.search(r'\[CORRECTION\](.+?)\[/CORRECTION\]', full_response)
    if correction_match:
        correction_text = correction_match.group(1).strip()
        # 从保存的回复中移除纠正标记
        clean_response = re.sub(r'\n?\[CORRECTION\].+?\[/CORRECTION\]', '', full_response)
        if clean_response != full_response:
            # 更新数据库中的回复（SQLite 不支持 UPDATE ORDER BY，用子查询）
            async with get_connection() as db:
                await db.execute(
                    "UPDATE messages SET content = ? WHERE id = (SELECT id FROM messages WHERE session_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 1)",
                    (clean_response, session_id),
                )
                await db.commit()
        # 纠正标记已从回复中移除，不再触发画像更新（对话不写入任何记忆）

    # 11. 发送结束标记
    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

    # 标记变化提醒为已展示
    for change_id in change_ids_to_mark:
        await mark_change_presented(change_id)

    # 12. 首条消息自动生成标题
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ? AND mode != 'system'",
            (session_id,)
        )
        row = await cursor.fetchone()
        if row and row["cnt"] <= 2:
            asyncio.create_task(_generate_session_title(session_id, user_message))


