from __future__ import annotations

import asyncio
import json
import re

import structlog

from app.database import get_connection, get_compile_sync_connection
from app.config import settings
from app.utils.llm import chat_completion

logger = structlog.get_logger()

# Semaphore to limit concurrent LLM calls
_LLM_SEMAPHORE = asyncio.Semaphore(2)


# 知识总结提示词：基于旧知识总结 + 最近10条时间线，重写知识总结（无字数限制）
COMPILE_TRUTH_PROMPT = """你是个人 Wiki 知识库的编译引擎。任务：基于旧的知识总结和最近的时间线事件，重写实体的【知识总结】。

【知识总结的要求】
1. 讲清楚该实体的来龙去脉和发展脉络，按时间顺序或主题组织
2. 从用户第一人称视角叙述（"我"），不是客观百科
3. 字数不限——根据事件复杂度自行决定篇幅，把故事讲完整
4. 自然融入关键时间节点作为证据，不要逐条罗列事件
5. 提炼关系模式、发展趋势、核心特征，而非平铺直叙
6. 如果旧知识总结已有内容，在其基础上增量更新，保留有效信息，补充新发展
7. 不要编造信息，只基于提供的证据

【输出格式】（严格遵守）
## Compiled Truth
[知识总结正文，无字数限制]

---
related_entities:
  - [[type:slug]] | 关系描述 | confidence: explicit
---

---
change_log:
  - YYYY-MM-DD: 变化描述
---

---
type_fields:
  field_name: value
---

当提到其他已知实体时，使用 [[slug]] 格式引用。
related_entities 的 confidence 可选值：explicit / frequent / implied / inferred
type_fields 根据实体类型输出：
- person: intimacy(0-100整数), relationship_type, first_seen(YYYY-MM-DD)
- place: place_type, related_activities, frequency
- event: event_type, time_range, participants
- concept: domain, related_concepts
- habit: habit_type, first_seen, last_seen, frequency_30d(整数)
- emotion_pattern: triggers(列表), emotion_type, recovery_method
- value_signal: signal_type, evidence_strength
- company: industry, relationship_type
- project: status, participants
- meeting: time, participants, topics
- media: media_type, rating(1-5), director, key_characters(列表), media_summary

如无变化，change_log 可省略。"""


# 摘要提示词：基于知识总结提取 ≤200 字摘要
SUMMARIZE_PROMPT = """你是个人 Wiki 知识库的摘要提取器。任务：基于下面的【知识总结】，提取一段≤200字的摘要。

【摘要的要求】
1. ≤200字，直接说清楚这个实体大概是什么、与用户的关系/互动/影响
2. 禁止概念性解释——对人物描述关系和互动，对概念描述用户理解和实践，对习惯描述频率和场景
3. 涵盖核心关系、关键特征、当前状态，让人一眼看懂
4. 不要罗列时间点，要提炼出最关键的信息
5. 从用户第一人称视角（"我"）

【输出格式】（严格遵守，只输出摘要正文，不要任何标题或标记）
[摘要正文，≤200字]"""


ENTITY_TYPE_FIELDS = {
    "person": ["intimacy", "relationship_type", "first_seen"],
    "place": ["place_type", "related_activities", "frequency"],
    "event": ["event_type", "time_range", "participants"],
    "concept": ["domain", "related_concepts"],
    "habit": ["habit_type", "first_seen", "last_seen", "frequency_30d"],
    "emotion_pattern": ["triggers", "emotion_type", "recovery_method"],
    "value_signal": ["signal_type", "evidence_strength"],
    "company": ["industry", "relationship_type"],
    "project": ["status", "participants"],
    "meeting": ["time", "participants", "topics"],
    "media": ["media_type", "rating", "director", "key_characters", "media_summary"],
}


async def update_backlinks_for_page(page_id: int, slug: str, compiled_truth: str, frontmatter: dict = None) -> None:
    async with get_connection() as db:
        # Delete all existing links from this page
        await db.execute("DELETE FROM links WHERE source_page_id = ?", (page_id,))

        # 1. Parse related_entities from frontmatter
        if frontmatter and isinstance(frontmatter.get("related_entities"), list):
            for entry in frontmatter["related_entities"]:
                if not isinstance(entry, str):
                    continue
                # Format: [[type:slug]] | relation | confidence: value
                # or: [[slug]] | relation | confidence: value
                match = re.match(r'\[\[(.+?)\]\]\s*\|\s*(.+?)\s*\|\s*confidence:\s*(\w+)', entry)
                if not match:
                    # Try without confidence
                    match = re.match(r'\[\[(.+?)\]\]\s*\|\s*(.+)', entry)
                    if match:
                        target_slug = match.group(1).strip()
                        if ':' in target_slug:
                            target_slug = target_slug.split(':', 1)[1]
                        relation = match.group(2).strip()
                        confidence = 'reference'
                    else:
                        continue
                else:
                    target_slug = match.group(1).strip()
                    if ':' in target_slug:
                        target_slug = target_slug.split(':', 1)[1]
                    relation = match.group(2).strip()
                    confidence = match.group(3).strip()

                cursor = await db.execute("SELECT id FROM pages WHERE slug = ?", (target_slug,))
                target_row = await cursor.fetchone()
                if target_row:
                    await db.execute(
                        "INSERT INTO links (source_page_id, target_page_id, link_type, confidence) VALUES (?, ?, ?, ?)",
                        (page_id, target_row["id"], relation, confidence),
                    )

        # 2. Parse [[slug]] from compiled_truth (simple references)
        # Extract [[slug]] references from compiled_truth first
        referenced_slugs = set(re.findall(r'\[\[([^\]]+)\]\]', compiled_truth))
        if referenced_slugs:
            # Only query pages that are actually referenced
            placeholders = ','.join(['?' for _ in referenced_slugs])
            cursor = await db.execute(
                f"SELECT slug, id FROM pages WHERE id != ? AND slug IN ({placeholders})",
                (page_id, *referenced_slugs),
            )
            rows = await cursor.fetchall()

            existing_targets = set()
            cursor2 = await db.execute("SELECT target_page_id FROM links WHERE source_page_id = ?", (page_id,))
            for row in await cursor2.fetchall():
                existing_targets.add(row["target_page_id"])

            for row in rows:
                other_slug = row["slug"]
                if other_slug and row["id"] not in existing_targets:
                    await db.execute(
                        "INSERT INTO links (source_page_id, target_page_id, link_type, confidence) VALUES (?, ?, 'reference', 'reference')",
                        (page_id, row["id"]),
                    )

        await db.commit()


# Reverse relationship inference rules
REVERSE_RELATIONS = {
    "同事": "同事",
    "同事关系": "同事关系",
    "朋友": "朋友",
    "室友": "室友",
    "同学": "同学",
    "领导": "下属",
    "下属": "领导",
    "员工": "雇主",
    "雇主": "员工",
    "老师": "学生",
    "学生": "老师",
    "一起跑步": "一起跑步",
    "一起聚餐": "一起聚餐",
    "合作": "合作",
    "参与者": "参与者",
    "成员": "组织",
    "组织": "成员",
    "实践者": "习惯",
    "习惯": "实践者",
    "常去": "常客",
    "常客": "常去",
}


# ---------------------------------------------------------------------------
# Synchronous DB helpers for compile_entity (called via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _read_page_for_compile(entity_tag: str) -> dict | None:
    """Read page data for compile_entity. Returns dict or None."""
    db = get_compile_sync_connection()
    cursor = db.execute("SELECT * FROM pages WHERE slug = ?", (entity_tag,))
    row = cursor.fetchone()
    if not row:
        return None
    page = dict(row)
    try:
        page["frontmatter"] = json.loads(page.get("frontmatter", "{}"))
    except (json.JSONDecodeError, TypeError):
        page["frontmatter"] = {}
    try:
        page["timeline"] = json.loads(page.get("timeline", "[]"))
    except (json.JSONDecodeError, TypeError):
        page["timeline"] = []
    page["summary"] = page.get("summary", "") or ""
    return page


def _create_page_for_compile(entity_tag: str) -> dict | None:
    """Create a placeholder page and return it. Returns dict or None."""
    db = get_compile_sync_connection()
    db.execute(
        "INSERT OR IGNORE INTO pages (slug, type, title, compiled_truth, timeline, frontmatter) "
        "VALUES (?, 'concept', ?, '', '[]', '{}')",
        (entity_tag, entity_tag),
    )
    db.commit()
    cursor = db.execute("SELECT * FROM pages WHERE slug = ?", (entity_tag,))
    row = cursor.fetchone()
    if not row:
        return None
    page = dict(row)
    try:
        page["frontmatter"] = json.loads(page.get("frontmatter", "{}"))
    except (json.JSONDecodeError, TypeError):
        page["frontmatter"] = {}
    try:
        page["timeline"] = json.loads(page.get("timeline", "[]"))
    except (json.JSONDecodeError, TypeError):
        page["timeline"] = []
    page["summary"] = page.get("summary", "") or ""
    return page


def _read_known_pages_for_compile(entity_tag: str) -> list[dict]:
    """Read known page slugs for cross-referencing."""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT slug, type, title FROM pages WHERE slug != ? ORDER BY updated_at DESC LIMIT 30",
        (entity_tag,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_timeline_events_for_compile(entity_tag: str) -> list[dict]:
    """Read timeline events related to this entity via related_page_slugs.
    取最近10条（timestamp DESC），包含 content 字段作为证据补充。"""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT timestamp, summary, content FROM timeline_events "
        "WHERE related_page_slugs LIKE ? "
        "ORDER BY timestamp DESC LIMIT 10",
        (f"%{entity_tag}%",),
    )
    return [dict(row) for row in cursor.fetchall()]


def _write_compile_result(
    entity_tag: str,
    page_id: int,
    old_truth: str,
    existing_timeline_json: str,
    new_truth: str,
    new_summary: str,
    timeline_json: str,
    frontmatter_json: str,
    frontmatter: dict,
) -> None:
    """Write all compile results in a single sync transaction.
    时间线驱动编译：不再标记信号，改为写入 last_compiled_at 时间戳。"""
    db = get_compile_sync_connection()

    # Save page version
    cursor = db.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 as next_version "
        "FROM page_versions WHERE page_id = ?",
        (page_id,),
    )
    row = cursor.fetchone()
    version_number = row["next_version"]
    db.execute(
        "INSERT INTO page_versions (page_id, version_number, compiled_truth_snapshot, timeline_snapshot) "
        "VALUES (?, ?, ?, ?)",
        (page_id, version_number, old_truth, existing_timeline_json),
    )

    # Update page（写入 last_compiled_at 用于时间线驱动判断）
    db.execute(
        "UPDATE pages SET compiled_truth=?, summary=?, timeline=?, frontmatter=?, "
        "updated_at=datetime('now','localtime'), last_compiled_at=datetime('now','localtime') WHERE slug=?",
        (new_truth, new_summary, timeline_json, frontmatter_json, entity_tag),
    )

    # Update FTS
    db.execute(
        "UPDATE pages_fts SET compiled_truth=? WHERE rowid=(SELECT rowid FROM pages WHERE slug=?)",
        (new_truth, entity_tag),
    )

    # 时间线驱动：不再需要标记信号 processed

    # Update backlinks
    db.execute("DELETE FROM links WHERE source_page_id = ?", (page_id,))

    # Parse related_entities from frontmatter
    if frontmatter.get("related_entities"):
        for entry in frontmatter["related_entities"]:
            if not isinstance(entry, str):
                continue
            match = re.match(r'\[\[(.+?)\]\]\s*\|\s*(.+?)\s*\|\s*confidence:\s*(\w+)', entry)
            if not match:
                match = re.match(r'\[\[(.+?)\]\]\s*\|\s*(.+)', entry)
                if match:
                    target_slug = match.group(1).strip()
                    if ':' in target_slug:
                        target_slug = target_slug.split(':', 1)[1]
                    relation = match.group(2).strip()
                    confidence = 'reference'
                else:
                    continue
            else:
                target_slug = match.group(1).strip()
                if ':' in target_slug:
                    target_slug = target_slug.split(':', 1)[1]
                relation = match.group(2).strip()
                confidence = match.group(3).strip()
            cursor = db.execute("SELECT id FROM pages WHERE slug = ?", (target_slug,))
            target_row = cursor.fetchone()
            if target_row:
                db.execute(
                    "INSERT INTO links (source_page_id, target_page_id, link_type, confidence) VALUES (?, ?, ?, ?)",
                    (page_id, target_row["id"], relation, confidence),
                )

    # Parse [[slug]] from compiled_truth
    referenced_slugs = set(re.findall(r'\[\[([^\]]+)\]\]', new_truth))
    if referenced_slugs:
        placeholders = ','.join(['?' for _ in referenced_slugs])
        cursor = db.execute(
            f"SELECT slug, id FROM pages WHERE id != ? AND slug IN ({placeholders})",
            (page_id, *referenced_slugs),
        )
        rows = cursor.fetchall()
        existing_targets = set()
        cursor2 = db.execute("SELECT target_page_id FROM links WHERE source_page_id = ?", (page_id,))
        for row in cursor2.fetchall():
            existing_targets.add(row["target_page_id"])
        for row in rows:
            if row["id"] not in existing_targets:
                db.execute(
                    "INSERT INTO links (source_page_id, target_page_id, link_type, confidence) VALUES (?, ?, 'reference', 'reference')",
                    (page_id, row["id"]),
                )

    # Commit everything in one transaction
    db.commit()

    return version_number


def _write_profiling_frontmatter(entity_tag: str, frontmatter_json: str) -> None:
    """Update frontmatter after profiling rules applied."""
    db = get_compile_sync_connection()
    db.execute(
        "UPDATE pages SET frontmatter = ? WHERE slug = ?",
        (frontmatter_json, entity_tag),
    )
    db.commit()


async def compile_entity(entity_tag: str) -> dict:
    """编译实体：基于旧知识总结 + 最近10条时间线，生成新的知识总结和摘要。
    时间线驱动，不再依赖信号。
    """
    # Read page using compile connection (avoid blocking main connection)
    page = await asyncio.to_thread(_read_page_for_compile, entity_tag)

    if not page:
        page = await asyncio.to_thread(_create_page_for_compile, entity_tag)

    if not page:
        return {"status": "error", "entity": entity_tag, "error": "Failed to create page"}

    old_truth = page.get("compiled_truth", "")

    # Get known page slugs for cross-referencing (limit to 30 most recent)
    known_pages = await asyncio.to_thread(_read_known_pages_for_compile, entity_tag)
    known_slugs = [f"{row['type']}:{row['slug']} ({row['title']})" for row in known_pages if row['slug']]
    slug_list_str = "\n".join(known_slugs[:30])

    # Get timeline events related to this entity (最近10条)
    timeline_events = await asyncio.to_thread(_read_timeline_events_for_compile, entity_tag)

    if len(timeline_events) < 1:
        return {"status": "skipped", "reason": "no_timeline_events", "count": 0}

    # 构造时间线文本块（含 content 作为证据补充）
    timeline_lines = []
    for evt in timeline_events:
        ts = (evt.get("timestamp", "") or "")[:10]
        summary = evt.get("summary", "")
        content = (evt.get("content", "") or "").strip()
        if ts and summary:
            line = f"- {ts}: {summary}"
            if content and content != summary:
                line += f"（证据：{content}）"
            timeline_lines.append(line)
    timeline_text_block = "\n".join(timeline_lines)

    # ========== 第一次 LLM 调用：生成知识总结 ==========
    try:
        async with _LLM_SEMAPHORE:
            truth_raw = await asyncio.wait_for(
                chat_completion(
                    messages=[m for m in [
                        {"role": "system", "content": COMPILE_TRUTH_PROMPT},
                        {"role": "user", "content": f"当前实体：{entity_tag}（类型：{page.get('type', 'concept')}）"},
                        {"role": "user", "content": f"已知实体列表（可用 [[slug]] 引用）：\n{slug_list_str}"} if slug_list_str else {"role": "user", "content": "已知实体列表：暂无"},
                        {"role": "user", "content": f"该实体的时间线事件（最近10条）：\n{timeline_text_block}"},
                        {"role": "user", "content": f"旧知识总结：\n{old_truth}"} if old_truth else {"role": "user", "content": "旧知识总结：无"},
                    ] if m is not None],
                    temperature=0.5,
                    max_tokens=20000,
                    purpose="实体知识总结编译",
                ),
                timeout=90.0,
            )
    except asyncio.TimeoutError:
        logger.error("compile_truth_timeout", entity=entity_tag)
        return {"status": "error", "entity": entity_tag, "error": "LLM call timed out (truth)"}
    except Exception as e:
        logger.error("compile_truth_llm_error", entity=entity_tag, error=str(e))
        return {"status": "error", "entity": entity_tag, "error": str(e)}

    # 解析知识总结输出
    new_truth = truth_raw
    related_entities = []
    change_log_entries = []
    type_fields = {}
    sub_content = ""

    # Extract Compiled Truth
    truth_match = re.search(r'##\s*Compiled\s*Truth\s*\n(.*?)(?=\n##\s*子内容|\n---|\Z)', truth_raw, re.DOTALL)
    if truth_match:
        new_truth = truth_match.group(1).strip()

    # Extract 子内容 (sub-content) section for media type entities
    sc_match = re.search(r'##\s*子内容\s*\n(.*?)(?=\n---|\Z)', truth_raw, re.DOTALL)
    if sc_match:
        sub_content = sc_match.group(1).strip()
        new_truth = re.sub(r'##\s*子内容\s*\n[\s\S]*?(?=\n---|\Z)', '', new_truth).strip()

    # Extract related_entities
    rel_match = re.search(r'---\s*related_entities:\s*\n([\s\S]*?)\n\s*---', truth_raw)
    if rel_match:
        rel_block = rel_match.group(1)
        for line in rel_block.strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                related_entities.append(line[2:].strip())

    # Extract change_log
    cl_match = re.search(r'---\s*change_log:\s*\n([\s\S]*?)\n\s*---', truth_raw)
    if cl_match:
        cl_block = cl_match.group(1)
        for line in cl_block.strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                change_log_entries.append(line[2:].strip())

    # Extract type_fields
    tf_match = re.search(r'---\s*type_fields:\s*\n([\s\S]*?)\n\s*---', truth_raw)
    if tf_match:
        tf_block = tf_match.group(1)
        for line in tf_block.strip().split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except (ValueError, TypeError):
                    pass
                type_fields[key] = value

    # ========== 第二次 LLM 调用：基于知识总结提取摘要 ==========
    try:
        async with _LLM_SEMAPHORE:
            summary_raw = await asyncio.wait_for(
                chat_completion(
                    messages=[
                        {"role": "system", "content": SUMMARIZE_PROMPT},
                        {"role": "user", "content": f"实体：{entity_tag}（类型：{page.get('type', 'concept')}）\n\n【知识总结】\n{new_truth}"},
                    ],
                    model=settings.llm.chat_mini_model,
                    temperature=0.3,
                    max_tokens=1000,
                    purpose="实体摘要提取",
                ),
                timeout=30.0,
            )
    except asyncio.TimeoutError:
        logger.error("compile_summary_timeout", entity=entity_tag)
        new_summary = ""
    except Exception as e:
        logger.error("compile_summary_llm_error", entity=entity_tag, error=str(e))
        new_summary = ""
    else:
        # 摘要直接取 LLM 输出（提示词要求只输出正文）
        new_summary = summary_raw.strip()
        # 去除可能残留的 markdown 标记
        new_summary = re.sub(r'^##\s*Summary\s*\n', '', new_summary, flags=re.IGNORECASE).strip()

    # ========== 构建 frontmatter ==========
    frontmatter = page.get("frontmatter", {})
    if isinstance(frontmatter, str):
        try:
            frontmatter = json.loads(frontmatter)
        except (json.JSONDecodeError, TypeError):
            frontmatter = {}
    if related_entities:
        frontmatter["related_entities"] = related_entities

    # Merge change_log into frontmatter (append new entries)
    existing_change_log = frontmatter.get("change_log", [])
    if isinstance(existing_change_log, str):
        existing_change_log = [existing_change_log]
    if change_log_entries:
        existing_change_log.extend(change_log_entries)
    if existing_change_log:
        frontmatter["change_log"] = existing_change_log

    if type_fields:
        frontmatter.update(type_fields)

    # Store sub-content for media type entities
    if sub_content:
        frontmatter["sub_content"] = sub_content

    page_id = page["id"]

    # timeline 字段保留原有内容（不再从信号追加）
    existing_timeline = page.get("timeline", [])
    if isinstance(existing_timeline, str):
        try:
            existing_timeline = json.loads(existing_timeline)
        except (json.JSONDecodeError, TypeError):
            existing_timeline = []
    existing_timeline_json = json.dumps(existing_timeline, ensure_ascii=False)
    timeline_json = existing_timeline_json
    frontmatter_json = json.dumps(frontmatter, ensure_ascii=False)

    # Apply profiling rules (inline, no DB calls)
    profiling_changes = _apply_profiling_rules_inline(
        page_type=page.get("type", "concept"),
        frontmatter=frontmatter,
        timeline=existing_timeline,
    )

    # If profiling changed frontmatter, update the json
    if profiling_changes:
        existing_cl = frontmatter.get("change_log", [])
        if isinstance(existing_cl, str):
            existing_cl = [existing_cl]
        existing_cl.extend(profiling_changes)
        frontmatter["change_log"] = existing_cl
        frontmatter_json = json.dumps(frontmatter, ensure_ascii=False)

    # Write all compile results via sync helper（不再传 signal_ids）
    version_number = await asyncio.to_thread(
        _write_compile_result,
        entity_tag,
        page_id,
        old_truth,
        existing_timeline_json,
        new_truth,
        new_summary,
        timeline_json,
        frontmatter_json,
        frontmatter,
    )

    # 同步实体向量到向量库（失败仅记日志，不影响编译主流程）
    try:
        from app.services.vector_store import vector_store
        from app.utils.embedding import embed_texts
        from datetime import datetime as _datetime

        # embedding 内容：title + summary + compiled_truth 全文
        title = page.get("title", "") or entity_tag
        embed_text = f"{title} {new_summary} {new_truth}".strip()
        vector = (await embed_texts([embed_text]))[0]

        # compiled_truth 前 300 字用于展示
        truth_preview = (new_truth or "")[:300]

        # aliases 从 pages 表获取
        aliases_str = ""
        try:
            db = get_compile_sync_connection()
            cursor = db.execute("SELECT aliases FROM pages WHERE slug = ?", (entity_tag,))
            row = cursor.fetchone()
            if row and row["aliases"]:
                aliases_str = row["aliases"]
        except Exception:
            pass

        await vector_store.upsert_entity(
            slug=entity_tag,
            title=title,
            entity_type=page.get("type", "concept"),
            summary=new_summary or "",
            compiled_truth_preview=truth_preview,
            aliases=aliases_str or "[]",
            updated_at=_datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            vector=vector,
        )
    except Exception as e:
        logger.warning("entity_vector_sync_failed", entity=entity_tag, error=str(e))

    # Update profile_changes system page
    if profiling_changes:
        try:
            await update_profile_changes(profiling_changes)
        except Exception as e:
            logger.error("update_profile_changes_failed", error=str(e))

    # Auto-detect frontmatter changes and write to profile_changes
    old_fm = page.get("frontmatter", {})
    if isinstance(old_fm, str):
        try:
            old_fm = json.loads(old_fm) if old_fm else {}
        except (json.JSONDecodeError, TypeError):
            old_fm = {}
    auto_changes = _detect_frontmatter_changes(entity_tag, old_fm, frontmatter)
    if auto_changes:
        try:
            await update_profile_changes(auto_changes)
        except Exception as e:
            logger.error("auto_profile_changes_failed", error=str(e))

    # Post-compile consistency check
    try:
        from app.services.consistency_checker import check_entity_consistency
        consistency = await check_entity_consistency(entity_tag, new_truth)
        if consistency.has_conflict:
            await _record_conflicts(entity_tag, consistency)
            if consistency.suggested_action == "auto_resolve":
                await _auto_resolve_conflict(entity_tag, consistency)
    except Exception as e:
        logger.error("consistency_check_failed", entity=entity_tag, error=str(e))

    # Link timeline events to this page
    try:
        from app.services.timeline import link_timeline_to_pages
        page_title = page.get("title", entity_tag)
        linked_count = await link_timeline_to_pages(entity_tag, page_title)
        if linked_count > 0:
            logger.info("linked_timeline_events", entity=entity_tag, count=linked_count)
    except Exception as e:
        logger.error("link_timeline_failed", error=str(e))

    return {
        "status": "completed",
        "entity": entity_tag,
        "timeline_events_used": len(timeline_events),
        "version": version_number,
        "summary_generated": bool(new_summary),
        "truth_length": len(new_truth),
        "related_entities_count": len(related_entities),
        "change_log_count": len(change_log_entries),
    }


# ---------------------------------------------------------------------------
# Conflict recording helpers
# ---------------------------------------------------------------------------

async def _record_conflicts(entity_tag: str, consistency_result) -> None:
    """Record conflicts from a ConsistencyResult into the conflicts table."""
    import uuid

    if not consistency_result.has_conflict:
        return

    from app.database import get_connection

    for conflict in consistency_result.conflicts:
        conflict_id = uuid.uuid4().hex
        async with get_connection() as db:
            await db.execute(
                "INSERT INTO conflicts (id, entity_tag, conflict_type, description, old_statement, new_statement, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    conflict_id,
                    entity_tag,
                    "entity_conflict",
                    conflict.conflict_description or f"{entity_tag} 与 {conflict.entity} 存在矛盾",
                    conflict.old_statement,
                    conflict.new_statement,
                    "pending" if consistency_result.suggested_action == "user_confirm" else "flagged",
                ),
            )
            await db.commit()

    logger.info("conflicts_recorded", entity=entity_tag, count=len(consistency_result.conflicts))


async def _record_conflicts_from_lint(lint_conflict: dict) -> None:
    """Record a conflict from lint results into the conflicts table."""
    import uuid

    from app.database import get_connection

    conflict_id = uuid.uuid4().hex
    entity = lint_conflict.get("entity", "unknown")
    description = f"{lint_conflict.get('conflict', '矛盾')} (涉及页面: {', '.join(lint_conflict.get('pages', []))})"

    async with get_connection() as db:
        await db.execute(
            "INSERT INTO conflicts (id, entity_tag, conflict_type, description, status) VALUES (?, ?, ?, ?, ?)",
            (conflict_id, entity, "lint_conflict", description, "pending"),
        )
        await db.commit()


async def _auto_resolve_conflict(entity_tag: str, consistency_result) -> None:
    """Auto-resolve time-evolution conflicts (e.g., '同事' → '前同事')."""
    from app.database import get_connection

    for conflict in consistency_result.conflicts:
        related_entity = conflict.entity

        # Mark the conflict as auto_resolved
        async with get_connection() as db:
            # Update the related entity's frontmatter if it's a time-evolution change
            cursor = await db.execute(
                "SELECT frontmatter FROM pages WHERE slug = ? AND type != 'system'",
                (related_entity,),
            )
            row = await cursor.fetchone()
            if row:
                try:
                    fm = json.loads(row["frontmatter"]) if row["frontmatter"] else {}
                except (json.JSONDecodeError, TypeError):
                    fm = {}

                # Add a status note for time-evolution
                old_status = fm.get("status", "")
                if "前" in conflict.new_statement or "已" in conflict.new_statement or "former" in conflict.new_statement.lower():
                    fm["status"] = "former"
                    await db.execute(
                        "UPDATE pages SET frontmatter = ? WHERE slug = ?",
                        (json.dumps(fm, ensure_ascii=False), related_entity),
                    )
                    await db.commit()

        # Record the auto-resolution
        await update_profile_changes([
            f"自动解决冲突：{entity_tag} 与 {related_entity} 的关系变化（{conflict.old_statement} → {conflict.new_statement}）"
        ])

        # Update conflict status
        async with get_connection() as db:
            await db.execute(
                "UPDATE conflicts SET status = 'auto_resolved', resolution = '时间变化自动解决', resolved_at = datetime('now', 'localtime') "
                "WHERE entity_tag = ? AND status = 'pending'",
                (entity_tag,),
            )
            await db.commit()

    logger.info("conflicts_auto_resolved", entity=entity_tag, count=len(consistency_result.conflicts))


def _detect_frontmatter_changes(entity_tag: str, old_fm: dict, new_fm: dict) -> list[str]:
    """Detect key frontmatter field changes between old and new versions.

    Compares predefined key fields and generates human-readable change descriptions.
    Returns a list of change entry strings for profile_changes.
    """
    from datetime import datetime

    watch_fields = [
        ("intimacy", "亲密度"),
        ("frequency_30d", "30天频次"),
        ("relationship_type", "关系类型"),
        ("confidence", "置信度"),
        ("status", "状态"),
    ]

    changes = []
    now_str = datetime.now().strftime("%Y-%m-%d")

    for field_key, field_label in watch_fields:
        old_val = old_fm.get(field_key)
        new_val = new_fm.get(field_key)
        if old_val is not None and new_val is not None and old_val != new_val:
            changes.append(
                f"[{now_str}] 实体「{entity_tag}」{field_label}变化：{old_val} → {new_val}"
            )
        elif old_val is None and new_val is not None:
            changes.append(
                f"[{now_str}] 实体「{entity_tag}」{field_label}新增：{new_val}"
            )

    return changes


def _apply_profiling_rules_inline(page_type: str, frontmatter: dict, timeline: list) -> list[str]:
    """Apply profiling rules inline (no DB calls). Returns change_log entries."""
    changes = []
    from datetime import datetime, timedelta

    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    ninety_days_ago = now - timedelta(days=90)

    # Rule: Habit formation
    if page_type == "habit":
        current_confidence = frontmatter.get("confidence", "implied")
        recent_30 = 0
        recent_90 = 0
        for entry in timeline:
            ts = entry.get("timestamp", "")
            try:
                entry_time = datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+08:00", ""))
                if entry_time >= thirty_days_ago:
                    recent_30 += 1
                if entry_time >= ninety_days_ago:
                    recent_90 += 1
            except (ValueError, AttributeError):
                recent_30 += 1
                recent_90 += 1

        if recent_30 >= 3 and current_confidence not in ("frequent", "explicit"):
            if current_confidence != "implied":
                changes.append(f"习惯形成推断：30天内出现{recent_30}次，置信度升级为implied")
                frontmatter["confidence"] = "implied"
        if recent_90 >= 10 and current_confidence != "explicit":
            if current_confidence != "frequent":
                changes.append(f"习惯确认推断：90天内出现{recent_90}次，置信度升级为frequent")
                frontmatter["confidence"] = "frequent"

        frontmatter["frequency_30d"] = recent_30
        frontmatter["last_seen"] = now.strftime("%Y-%m-%d")
        if not frontmatter.get("first_seen") and timeline:
            earliest = None
            for entry in timeline:
                ts = entry.get("timestamp", "")
                if ts and (earliest is None or ts < earliest):
                    earliest = ts
            if earliest:
                frontmatter["first_seen"] = earliest[:10]

    # Auto-update person type-specific fields
    if page_type == "person":
        if not frontmatter.get("first_seen") and timeline:
            earliest = None
            for entry in timeline:
                ts = entry.get("timestamp", "")
                if ts and (earliest is None or ts < earliest):
                    earliest = ts
            if earliest:
                frontmatter["first_seen"] = earliest[:10]

    return changes


# ---------------------------------------------------------------------------
# Synchronous DB helpers for update_profile_changes
# ---------------------------------------------------------------------------

def _read_profile_changes_truth() -> str:
    db = get_compile_sync_connection()
    cursor = db.execute("SELECT compiled_truth FROM pages WHERE slug = 'profile_changes'")
    row = cursor.fetchone()
    return row["compiled_truth"] if row else ""


def _write_profile_changes(updated_truth: str) -> None:
    db = get_compile_sync_connection()
    db.execute(
        "INSERT OR REPLACE INTO pages (slug, type, title, compiled_truth, summary, timeline, frontmatter, updated_at) "
        "VALUES ('profile_changes', 'system', '画像变化记录', ?, '记录实体画像的变化和消退预警', '[]', '{}', datetime('now','localtime'))",
        (updated_truth,),
    )
    db.commit()


async def update_profile_changes(change_entries: list[str]) -> None:
    """Write changes to the profile_changes system page."""
    if not change_entries:
        return

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d")

    existing_truth = await asyncio.to_thread(_read_profile_changes_truth)

    new_entries = "\n".join([f"[{timestamp}] {entry}" for entry in change_entries])
    updated_truth = f"{new_entries}\n\n{existing_truth}" if existing_truth else new_entries

    await asyncio.to_thread(_write_profile_changes, updated_truth)


# ---------------------------------------------------------------------------
# Synchronous DB helpers for update_wiki_index
# ---------------------------------------------------------------------------

def _read_pages_for_index() -> list[dict]:
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT slug, type, title, summary, frontmatter, updated_at FROM pages "
        "WHERE type != 'system' ORDER BY updated_at DESC LIMIT 100"
    )
    return [dict(row) for row in cursor.fetchall()]


def _write_wiki_index(index_truth: str, summary_text: str) -> None:
    db = get_compile_sync_connection()
    db.execute(
        "INSERT OR REPLACE INTO pages (slug, type, title, compiled_truth, summary, timeline, frontmatter, updated_at) "
        "VALUES ('index', 'system', '知识库索引', ?, ?, '[]', '{}', datetime('now','localtime'))",
        (index_truth, summary_text),
    )
    db.commit()


async def update_wiki_index() -> None:
    """Update the wiki/index system page with summary index table."""
    rows = await asyncio.to_thread(_read_pages_for_index)

    lines = ["| 实体 | 类型 | 摘要 | 标签 | 最后更新 |", "|------|------|------|------|----------|"]
    for row in rows:
        slug = row["slug"] or ""
        ptype = row["type"] or ""
        summary = (row["summary"] or "")[:50]
        tags_str = ""
        try:
            fm = json.loads(row["frontmatter"]) if row["frontmatter"] else {}
            tags_data = fm.get("tags", [])
            if isinstance(tags_data, list):
                tags_str = ",".join(str(t) for t in tags_data[:3])
        except (json.JSONDecodeError, TypeError):
            tags_str = ""
        updated = (row["updated_at"] or "")[:10]
        lines.append(f"| {slug} | {ptype} | {summary} | {tags_str} | {updated} |")

    index_truth = "\n".join(lines)
    await asyncio.to_thread(_write_wiki_index, index_truth, f"共{len(rows)}个实体的摘要索引")


# ---------------------------------------------------------------------------
# Synchronous DB helpers for append_wiki_log
# ---------------------------------------------------------------------------

def _read_change_log_truth() -> str:
    db = get_compile_sync_connection()
    cursor = db.execute("SELECT compiled_truth FROM pages WHERE slug = 'change_log'")
    row = cursor.fetchone()
    return row["compiled_truth"] if row else ""


def _write_change_log(updated_truth: str) -> None:
    db = get_compile_sync_connection()
    db.execute(
        "INSERT OR REPLACE INTO pages (slug, type, title, compiled_truth, summary, timeline, frontmatter, updated_at) "
        "VALUES ('change_log', 'system', '操作日志', ?, '知识库操作日志', '[]', '{}', datetime('now','localtime'))",
        (updated_truth,),
    )
    db.commit()


async def append_wiki_log(action: str, detail: str) -> None:
    """Append an entry to the wiki/log system page."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    existing_truth = await asyncio.to_thread(_read_change_log_truth)

    new_entry = f"[{timestamp}] {action} | {detail}"
    updated_truth = f"{new_entry}\n{existing_truth}" if existing_truth else new_entry

    await asyncio.to_thread(_write_change_log, updated_truth)


# ---------------------------------------------------------------------------
# Synchronous DB helpers for run_compile_cycle
# ---------------------------------------------------------------------------

def _read_entities_with_new_timeline() -> list[dict]:
    """读取有新时间线事件待编译的实体（时间线驱动）。
    判断条件：timeline_events.created_at > pages.last_compiled_at（或 last_compiled_at 为空）。
    返回 [{slug, last_compiled_at}, ...]
    """
    db = get_compile_sync_connection()
    cursor = db.execute(
        """
        SELECT DISTINCT p.slug, p.last_compiled_at
        FROM pages p
        WHERE p.type != 'system'
        AND EXISTS (
            SELECT 1 FROM timeline_events te
            WHERE te.related_page_slugs LIKE '%' || p.slug || '%'
            AND te.created_at > COALESCE(p.last_compiled_at, '1970-01-01')
        )
        ORDER BY p.slug
        """
    )
    return [dict(row) for row in cursor.fetchall()]


async def run_compile_cycle() -> dict:
    """时间线驱动的编译循环：扫描有新时间线事件的实体并触发编译。"""
    try:
        rows = await asyncio.wait_for(asyncio.to_thread(_read_entities_with_new_timeline), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("read_entities_with_new_timeline_timeout")
        return {"cycle_completed": False, "entities_compiled": 0, "entities_skipped": 0, "error": "read_entities_timeout"}
    except Exception as e:
        logger.error("read_entities_with_new_timeline_error", error=str(e))
        return {"cycle_completed": False, "entities_compiled": 0, "entities_skipped": 0, "error": str(e)}

    entities_compiled = 0
    entities_skipped = 0
    MAX_COMPILE_PER_CYCLE = 3  # Limit compilations per cycle to avoid blocking

    for row in rows:
        if entities_compiled >= MAX_COMPILE_PER_CYCLE:
            break
        tag = row["slug"]
        try:
            result = await compile_entity(tag)
            if result.get("status") == "completed":
                entities_compiled += 1
                logger.info(
                    "compile_entity_completed",
                    entity=tag,
                    timeline_events_used=result.get("timeline_events_used"),
                )
            else:
                entities_skipped += 1
            # Yield control to event loop between compilations
            await asyncio.sleep(2)
        except Exception as e:
            logger.error("compile_entity_failed", entity=tag, error=str(e))
            entities_skipped += 1

    # Update wiki/index after compile cycle
    try:
        await update_wiki_index()
    except Exception as e:
        logger.error("update_wiki_index_failed", error=str(e))

    # Auto lint after compile cycle if entities were compiled
    if entities_compiled > 0:
        try:
            lint_result = await asyncio.to_thread(_lint_knowledge_base)
            contradictions = lint_result.get("contradictions", [])
            if contradictions:
                await update_profile_changes([f"[自动Lint] 发现{len(contradictions)}个矛盾"])
                for c in contradictions[:3]:
                    await _record_conflicts_from_lint(c)
        except Exception as e:
            logger.error("auto_lint_failed", error=str(e))

    # Auto expire stale feedback
    try:
        from app.services.feedback_service import expire_feedback
        expired_count = await expire_feedback()
        if expired_count > 0:
            logger.info("feedback_expired", count=expired_count)
    except Exception as e:
        logger.error("feedback_expire_failed", error=str(e))

    return {
        "cycle_completed": True,
        "entities_compiled": entities_compiled,
        "entities_skipped": entities_skipped,
    }


# ---------------------------------------------------------------------------
# Synchronous DB helpers for lint_knowledge_base
# ---------------------------------------------------------------------------

def _lint_knowledge_base() -> dict:
    """Run all lint queries synchronously and return results."""
    db = get_compile_sync_connection()
    result = {
        "orphan_pages": [],
        "missing_pages": [],
        "contradictions": [],
        "stale_pages": [],
    }

    # 1. Orphan pages: no incoming or outgoing links, non-system
    cursor = db.execute("""
        SELECT p.slug, p.title, p.type FROM pages p
        WHERE p.type != 'system'
        AND p.id NOT IN (SELECT source_page_id FROM links)
        AND p.id NOT IN (SELECT target_page_id FROM links)
    """)
    for row in cursor.fetchall():
        result["orphan_pages"].append({"slug": row["slug"], "title": row["title"], "type": row["type"]})

    # 2. Missing pages: referenced in related_entities or [[slug]] but don't exist
    cursor = db.execute("SELECT slug, frontmatter, compiled_truth FROM pages WHERE type != 'system'")
    referenced_slugs = set()
    existing_slugs = set()

    cursor2 = db.execute("SELECT slug FROM pages")
    for row in cursor2.fetchall():
        existing_slugs.add(row["slug"])

    cursor = db.execute("SELECT slug, frontmatter, compiled_truth FROM pages WHERE type != 'system'")
    for row in cursor.fetchall():
        # Check related_entities
        try:
            fm = json.loads(row["frontmatter"]) if row["frontmatter"] else {}
        except (json.JSONDecodeError, TypeError):
            fm = {}

        rel_entities = fm.get("related_entities", [])
        if isinstance(rel_entities, list):
            for entry in rel_entities:
                if not isinstance(entry, str):
                    continue
                match = re.match(r'\[\[(.+?)\]\]', entry)
                if match:
                    ref = match.group(1)
                    slug = ref.split(':', 1)[1] if ':' in ref else ref
                    if slug not in existing_slugs:
                        referenced_slugs.add(slug)

        # Check [[slug]] in compiled_truth
        truth = row["compiled_truth"] or ""
        for m in re.finditer(r'\[\[(.+?)\]\]', truth):
            ref = m.group(1)
            slug = ref.split(':', 1)[1] if ':' in ref else ref
            if slug not in existing_slugs:
                referenced_slugs.add(slug)

    for slug in referenced_slugs:
        result["missing_pages"].append(slug)

    # 3. Contradiction detection: same entity described differently in different pages
    cursor = db.execute("SELECT slug, frontmatter FROM pages WHERE type != 'system'")
    entity_relations = {}  # slug -> {relation_type: set of descriptions}
    for row in cursor.fetchall():
        try:
            fm = json.loads(row["frontmatter"]) if row["frontmatter"] else {}
        except (json.JSONDecodeError, TypeError):
            fm = {}
        rel_entities = fm.get("related_entities", [])
        if isinstance(rel_entities, list):
            for entry in rel_entities:
                if not isinstance(entry, str):
                    continue
                match = re.match(r'\[\[(.+?)\]\]\s*\|\s*(.+?)\s*\|\s*confidence:', entry)
                if match:
                    target_slug = match.group(1).split(':', 1)[-1] if ':' in match.group(1) else match.group(1)
                    relation = match.group(2).strip()
                    if target_slug not in entity_relations:
                        entity_relations[target_slug] = {}
                    if relation not in entity_relations[target_slug]:
                        entity_relations[target_slug][relation] = set()
                    entity_relations[target_slug][relation].add(row["slug"])

    # Check for contradictory descriptions
    contradiction_keywords = [
        ("同事", "前同事"), ("朋友", "前朋友"), ("在用", "已弃用"),
        ("活跃", "消退"), ("形成中", "已消退"),
    ]
    for slug, relations in entity_relations.items():
        relation_types = set(relations.keys())
        for kw1, kw2 in contradiction_keywords:
            if kw1 in relation_types and kw2 in relation_types:
                result["contradictions"].append({
                    "entity": slug,
                    "conflict": f"{kw1} vs {kw2}",
                    "pages": list(relations[kw1] | relations[kw2]),
                })

    # 4. Stale pages: not updated in 90 days, non-system
    cursor = db.execute("""
        SELECT slug, title, type, updated_at FROM pages
        WHERE type != 'system'
        AND updated_at < datetime('now', 'localtime', '-90 days')
    """)
    for row in cursor.fetchall():
        result["stale_pages"].append({
            "slug": row["slug"],
            "title": row["title"],
            "type": row["type"],
            "last_updated": row["updated_at"],
        })

    return result


async def lint_knowledge_base() -> dict:
    """Run health checks on the knowledge base."""
    result = await asyncio.to_thread(_lint_knowledge_base)

    # Log lint results
    total_issues = len(result["orphan_pages"]) + len(result["missing_pages"]) + len(result["contradictions"]) + len(result["stale_pages"])
    if total_issues > 0:
        await append_wiki_log("lint", f"发现{total_issues}个问题：孤立{len(result['orphan_pages'])}，缺失{len(result['missing_pages'])}，矛盾{len(result['contradictions'])}，过期{len(result['stale_pages'])}")

    return result


def _detect_merge_candidates() -> list[dict]:
    """Detect pages that might be candidates for merging."""
    db = get_compile_sync_connection()
    suggestions = []

    # Get all non-system pages
    cursor = db.execute("SELECT slug, type, title, aliases, frontmatter FROM pages WHERE type != 'system'")
    pages = []
    for row in cursor.fetchall():
        page = dict(row)
        try:
            page["aliases"] = json.loads(page.get("aliases", "[]")) if page.get("aliases") else []
        except (json.JSONDecodeError, TypeError):
            page["aliases"] = []
        try:
            page["frontmatter"] = json.loads(page.get("frontmatter", "{}")) if page.get("frontmatter") else {}
        except (json.JSONDecodeError, TypeError):
            page["frontmatter"] = {}
        pages.append(page)

    # Helper: simple string similarity using longest common subsequence ratio
    def similarity(s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        # Simple ratio based on common characters
        len_s1, len_s2 = len(s1), len(s2)
        if abs(len_s1 - len_s2) / max(len_s1, len_s2) > 0.5:
            return 0.0
        # Use edit distance approximation
        matches = sum(1 for a, b in zip(s1, s2) if a == b)
        return 2.0 * matches / (len_s1 + len_s2)

    # Group by type for comparison
    by_type: dict[str, list[dict]] = {}
    for p in pages:
        t = p["type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(p)

    seen_pairs = set()

    for ptype, type_pages in by_type.items():
        for i, p1 in enumerate(type_pages):
            for j in range(i + 1, len(type_pages)):
                p2 = type_pages[j]
                pair_key = tuple(sorted([p1["slug"], p2["slug"]]))
                if pair_key in seen_pairs:
                    continue

                reason = None

                # Check 1: Title similarity > 80%
                sim = similarity(p1["title"], p2["title"])
                if sim > 0.8:
                    reason = f"标题相似度 {sim:.0%}：「{p1['title']}」vs「{p2['title']}」"

                # Check 2: One's title is in another's aliases
                if not reason:
                    if p1["title"] in p2.get("aliases", []):
                        reason = f"「{p1['title']}」是「{p2['title']}」的别名"
                    elif p2["title"] in p1.get("aliases", []):
                        reason = f"「{p2['title']}」是「{p1['title']}」的别名"

                # Check 3: Title substring relationship (length >= 2, same type)
                if not reason:
                    t1 = p1["title"] or ""
                    t2 = p2["title"] or ""
                    if len(t1) >= 2 and len(t2) >= 2 and t1 != t2:
                        if t1 in t2:
                            reason = f"名称包含关系：「{t1}」是「{t2}」的子串"
                        elif t2 in t1:
                            reason = f"名称包含关系：「{t2}」是「{t1}」的子串"

                if reason:
                    seen_pairs.add(pair_key)
                    # Pick the one with more content as target
                    if len(p1.get("compiled_truth", "") or "") >= len(p2.get("compiled_truth", "") or ""):
                        target, source = p1, p2
                    else:
                        target, source = p2, p1
                    suggestions.append({
                        "target_slug": target["slug"],
                        "target_title": target["title"],
                        "source_slugs": [source["slug"]],
                        "source_titles": [source["title"]],
                        "reason": reason,
                        "type": ptype,
                    })

    return suggestions


async def detect_merge_candidates() -> list[dict]:
    """Detect pages that might be candidates for merging."""
    return await asyncio.to_thread(_detect_merge_candidates)


async def start_compile_scheduler() -> None:
    """Run the compile scheduler in the main event loop, using a separate DB connection."""
    logger.info("compile_scheduler_started", interval_seconds=300)
    await asyncio.sleep(30)  # Wait 30s before first compile cycle
    while True:
        try:
            logger.info("compile_cycle_starting")
            result = await run_compile_cycle()
            logger.info(
                "compile_cycle_completed",
                compiled=result["entities_compiled"],
                skipped=result["entities_skipped"],
            )
        except Exception as e:
            logger.error("compile_cycle_failed", error=str(e))

        # Auto-confirm old timeline events
        try:
            from app.services.timeline import auto_confirm_old_events
            confirmed_count = await auto_confirm_old_events()
            if confirmed_count > 0:
                logger.info("auto_confirmed_timeline_events", count=confirmed_count)
        except Exception as e:
            logger.error("auto_confirm_failed", error=str(e))

        await asyncio.sleep(300)


async def compile_entity_manual(entity_tag: str) -> dict:
    try:
        return await compile_entity(entity_tag)
    except Exception as e:
        logger.error("compile_entity_manual_failed", entity_tag=entity_tag, error=str(e))
        return {"status": "error", "entity": entity_tag, "error": str(e)}


# ---------------------------------------------------------------------------
# Synchronous DB helpers for generate_weekly_profile
# ---------------------------------------------------------------------------

def _read_previous_weekly_profile(week_key: str) -> str | None:
    """查找上一周（7天前，时间跨度不大于8天）的周画像文本。"""
    from datetime import datetime, timedelta

    db = get_compile_sync_connection()
    # week_key 格式为 YYYYWW，如 202624
    # 尝试查找前一周的 slug
    try:
        year = int(week_key[:4])
        week = int(week_key[4:6])
        # 计算本周一的日期，减7天得到上周一
        jan4 = datetime(year, 1, 4)
        week1_monday = jan4 - timedelta(days=jan4.weekday())
        this_monday = week1_monday + timedelta(weeks=week - 1)
        prev_monday = this_monday - timedelta(days=7)
        prev_week_key = prev_monday.strftime("%Y%W")
    except (ValueError, IndexError):
        return None

    row = db.execute(
        "SELECT compiled_truth FROM pages WHERE type = 'system' AND slug = ? AND compiled_truth != ''",
        (f"weekly_profile_{prev_week_key}",),
    ).fetchone()
    return dict(row)["compiled_truth"] if row else None


def _read_previous_monthly_profile(month_key: str) -> str | None:
    """查找上月（时间跨度不大于35天）的月画像文本。"""
    db = get_compile_sync_connection()
    try:
        year = int(month_key[:4])
        month = int(month_key[4:6])
        if month == 1:
            prev_key = f"{year - 1}12"
        else:
            prev_key = f"{year}{month - 1:02d}"
    except (ValueError, IndexError):
        return None

    row = db.execute(
        "SELECT compiled_truth FROM pages WHERE type = 'system' AND slug = ? AND compiled_truth != ''",
        (f"monthly_profile_{prev_key}",),
    ).fetchone()
    return dict(row)["compiled_truth"] if row else None


def _read_self_entity_summaries(days: int = 90) -> list[dict]:
    """Read entity summaries for self-related types only (habit, emotion_pattern, value_signal, self).

    Used by overall profile to focus on the user's own personality traits
    rather than external entities like other people or companies.
    """
    from datetime import datetime, timedelta

    db = get_compile_sync_connection()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor = db.execute(
        "SELECT DISTINCT p.slug, p.type, p.title, p.summary, p.frontmatter "
        "FROM pages p "
        "INNER JOIN raw_signals rs ON rs.entity_tags LIKE '%' || p.slug || '%' "
        "WHERE p.type IN ('habit', 'emotion_pattern', 'value_signal', 'self') "
        "AND rs.created_at >= ? "
        "ORDER BY p.updated_at DESC LIMIT 30",
        (cutoff,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_timeline_events_by_date_range(start_date: str, end_date: str, limit: int = 500) -> list[dict]:
    """读取指定日期范围内的 timeline_events，用于画像生成。

    Args:
        start_date: 起始日期（含），格式 YYYY-MM-DD
        end_date: 结束日期（含），格式 YYYY-MM-DD
        limit: 最多返回条目数
    """
    db = get_compile_sync_connection()
    # end_date 取当天结束，故加 ' 23:59:59' 以包含当天所有事件
    cursor = db.execute(
        "SELECT timestamp, event_type, summary, content, sentiment, emotional_keywords, "
        "importance_score, is_milestone "
        "FROM timeline_events WHERE timestamp >= ? AND timestamp <= ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (start_date, f"{end_date} 23:59:59", limit),
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_important_timeline_events(limit: int = 50) -> list[dict]:
    """读取重要的 timeline_events（里程碑 + 高重要性事件），用于核心人格生成。"""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT timestamp, event_type, summary, content, sentiment, emotional_keywords, "
        "importance_score, is_milestone "
        "FROM timeline_events WHERE is_milestone = 1 OR importance_score >= 0.7 "
        "ORDER BY importance_score DESC, timestamp DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _format_timeline_events(events: list[dict], max_count: int = 50) -> str:
    """将 timeline_events 列表格式化为文本块。"""
    lines = []
    for ev in events[:max_count]:
        text = f"[{ev.get('timestamp', '')}] [{ev.get('event_type', '')}] {ev.get('summary', '')}"
        if ev.get("sentiment"):
            text += f" (情绪: {ev['sentiment']})"
        if ev.get("emotional_keywords"):
            text += f" [关键词: {ev['emotional_keywords']}]"
        if ev.get("is_milestone"):
            text += " ★里程碑"
        lines.append(text)
    return chr(10).join(lines)


def _write_weekly_profile(slug: str, title: str, profile_text: str, summary: str) -> None:
    db = get_compile_sync_connection()
    db.execute(
        "INSERT OR REPLACE INTO pages (slug, type, title, compiled_truth, summary, timeline, frontmatter, updated_at) "
        "VALUES (?, 'system', ?, ?, ?, '[]', '{}', datetime('now','localtime'))",
        (slug, title, profile_text, summary),
    )
    db.commit()


async def _refine_profile_with_loop(
    draft_text: str,
    source_materials: str,
    profile_type: str,
    max_rounds: int = 2,
    quality_threshold: float = 0.7,
) -> str:
    """Generate → Evaluate → Revise loop until quality threshold met or max rounds reached."""
    from app.services.consistency_checker import check_profile_quality

    current_text = draft_text

    for round_idx in range(max_rounds):
        quality = await check_profile_quality(current_text, source_materials, profile_type)
        if quality.score >= quality_threshold:
            # Quality passed — check feedback compliance
            try:
                from app.services.feedback_service import check_feedback_compliance
                compliance = await check_feedback_compliance(current_text, profile_type)
                if not compliance["compliant"] and compliance["violations_text"]:
                    logger.info("profile_feedback_violation", profile_type=profile_type, round=round_idx)
                    revision_prompt = f"你生成的画像违反了以下用户修正建议：\n{compliance['violations_text']}\n\n请修订画像，遵守上述建议。保持原有结构和长度。"
                    try:
                        current_text = await chat_completion(
                            messages=[
                                {"role": "user", "content": revision_prompt},
                                {"role": "assistant", "content": current_text},
                                {"role": "user", "content": "请修订上述画像。"},
                            ],
                            temperature=0.3,
                            max_tokens=20000,
                            purpose=f"{profile_type}画像反馈修订",
                        )
                    except Exception as e:
                        logger.error("feedback_revision_failed", profile_type=profile_type, error=str(e))
            except Exception as e:
                logger.error("feedback_compliance_check_failed", profile_type=profile_type, error=str(e))

            logger.info("profile_quality_passed", profile_type=profile_type, score=quality.score, round=round_idx)
            break

        logger.info("profile_quality_below_threshold", profile_type=profile_type, score=quality.score, round=round_idx, issues=len(quality.issues))

        issues_text = "\n".join(f"- {issue}" for issue in quality.issues)
        suggestions_text = "\n".join(f"- {s}" for s in quality.suggestions)

        revision_prompt = f"""你之前生成的{profile_type}画像存在以下问题：
{issues_text}

改进建议：
{suggestions_text}

请修订画像文本，解决上述问题。保持原有结构和长度。"""

        try:
            current_text = await chat_completion(
                messages=[
                    {"role": "user", "content": revision_prompt},
                    {"role": "assistant", "content": current_text},
                    {"role": "user", "content": "请修订上述画像。"},
                ],
                temperature=0.3,
                max_tokens=20000,
                purpose=f"{profile_type}画像修订",
            )
        except Exception as e:
            logger.error("profile_revision_failed", profile_type=profile_type, round=round_idx, error=str(e))
            break

    return current_text


async def generate_weekly_profile() -> dict:
    """Generate a weekly profile summarizing the week's activities and patterns."""
    from datetime import datetime, timedelta

    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday
    week_key = week_start.strftime("%Y%W")
    slug = f"weekly_profile_{week_key}"

    # Read this week's timeline events as the PRIMARY input
    week_start_str = week_start.strftime("%Y-%m-%d")
    week_end_str = week_end.strftime("%Y-%m-%d")
    events = await asyncio.to_thread(_read_timeline_events_by_date_range, week_start_str, week_end_str, 500)

    events_text = _format_timeline_events(events, max_count=50)

    # Read previous week's profile for comparison
    prev_week_profile = await asyncio.to_thread(_read_previous_weekly_profile, week_key)

    prev_week_section = ""
    if prev_week_profile:
        prev_week_section = f"\n\n上周画像（请进行比较，得出变化趋势）：\n{prev_week_profile}"

    prompt = f"""请根据以下数据撰写本周画像（{week_start.strftime('%Y-%m-%d')} 至 {week_end.strftime('%Y-%m-%d')}）。

本周时间线事件（共{len(events)}条）：
{events_text}
{prev_week_section}

请撰写本周画像，包含：
1. 工作与学习：投入时间、关键进展
2. 情绪状态：整体情绪、波动事件
3. 习惯追踪：哪些习惯保持、哪些波动
4. 社交活跃度：与人互动情况
5. 关键事件：本周最重要的事
6. 下周关注点

如果有上周画像，请在各维度中增加与上周的对比，指出变化趋势。
请用中文撰写，客观简洁，200-400字。"""

    # Inject user feedback constraints
    try:
        from app.services.feedback_service import build_feedback_prompt_section
        feedback_section = await build_feedback_prompt_section("weekly_profile", f"周画像 {week_key}")
        if feedback_section:
            prompt += f"\n\n{feedback_section}"
    except Exception as e:
        logger.error("feedback_inject_failed", profile_type="weekly", error=str(e))

    profile_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="周画像生成",
    )

    # Quality refinement loop
    source_materials = f"本周时间线事件摘要：{events_text[:500]}"
    profile_text = await _refine_profile_with_loop(profile_text, source_materials, "weekly")

    await asyncio.to_thread(
        _write_weekly_profile,
        slug,
        f"周画像 {week_start.strftime('%Y-%m-%d')}~{week_end.strftime('%Y-%m-%d')}",
        profile_text,
        f"本周画像：{week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}",
    )

    await append_wiki_log("profile", f"生成周画像 {slug}")

    return {"status": "completed", "slug": slug}


# ---------------------------------------------------------------------------
# Synchronous DB helpers for generate_monthly_profile
# ---------------------------------------------------------------------------

def _read_weekly_profiles(year_str: str) -> list[dict]:
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, slug FROM pages WHERE type = 'system' AND slug LIKE ? AND compiled_truth != '' "
        "ORDER BY slug DESC LIMIT 4",
        (f"weekly_profile_{year_str}%",),
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_profile_changes_truth() -> str:
    db = get_compile_sync_connection()
    cursor = db.execute("SELECT compiled_truth FROM pages WHERE slug = 'profile_changes'")
    row = cursor.fetchone()
    return row["compiled_truth"] if row else ""


def _write_monthly_profile(slug: str, title: str, profile_text: str, summary: str) -> None:
    db = get_compile_sync_connection()
    # Check if page already exists to save version history
    existing = db.execute(
        "SELECT id, compiled_truth FROM pages WHERE slug = ?", (slug,)
    ).fetchone()
    if existing and existing["compiled_truth"]:
        # Save current version before overwriting
        ver_count = db.execute(
            "SELECT COUNT(*) as cnt FROM page_versions WHERE page_id = ?", (existing["id"],)
        ).fetchone()["cnt"]
        db.execute(
            "INSERT INTO page_versions (page_id, version_number, compiled_truth_snapshot, timeline_snapshot) "
            "VALUES (?, ?, ?, '[]')",
            (existing["id"], ver_count + 1, existing["compiled_truth"]),
        )
    db.execute(
        "INSERT OR REPLACE INTO pages (slug, type, title, compiled_truth, summary, timeline, frontmatter, updated_at) "
        "VALUES (?, 'system', ?, ?, ?, '[]', '{}', datetime('now','localtime'))",
        (slug, title, profile_text, summary),
    )
    db.commit()


async def generate_monthly_profile() -> dict:
    """Generate a monthly profile summarizing the month's patterns and changes."""
    from datetime import datetime

    now = datetime.now()
    month_key = now.strftime("%Y%m")
    slug = f"monthly_profile_{month_key}"

    # Read weekly profiles for this month
    weekly_profiles = await asyncio.to_thread(_read_weekly_profiles, now.strftime("%Y"))

    # Read this month's timeline events as the PRIMARY input
    month_events = await asyncio.to_thread(_read_monthly_events, month_key)
    events_text = _format_timeline_events(month_events, max_count=80)

    # Read profile_changes
    changes_text = await asyncio.to_thread(_read_profile_changes_truth)

    weekly_texts = [wp["compiled_truth"] for wp in weekly_profiles if wp["compiled_truth"]]

    # Read previous month's profile for comparison
    prev_month_profile = await asyncio.to_thread(_read_previous_monthly_profile, month_key)

    prev_month_section = ""
    if prev_month_profile:
        prev_month_section = f"\n\n上月画像（请进行比较，得出变化趋势）：\n{prev_month_profile}"

    prompt = f"""请根据以下数据撰写本月画像（{now.strftime('%Y年%m月')}）。

本月时间线事件（共{len(month_events)}条）：
{events_text}

本月周画像：
{chr(10).join(weekly_texts[:4])}

画像变化记录：
{changes_text[:1000] if changes_text else '暂无'}
{prev_month_section}

请撰写月画像，包含：
1. 行为模式变化趋势：哪些习惯在形成/消退
2. 新习惯形成：本月新出现的重复行为
3. 旧习惯消退：之前稳定但本月减少的行为
4. 关系变化：人际关系的重要变化
5. 情绪模式：本月主要的情绪模式
6. 价值观信号：本月体现的价值观倾向
7. 下月关注点

如果有上月画像，请在各维度中增加与上月的对比，指出变化趋势。
请用中文撰写，客观简洁，300-500字。"""

    # Inject user feedback constraints
    try:
        from app.services.feedback_service import build_feedback_prompt_section
        feedback_section = await build_feedback_prompt_section("monthly_profile", f"月画像 {now.strftime('%Y年%m月')}")
        if feedback_section:
            prompt += f"\n\n{feedback_section}"
    except Exception as e:
        logger.error("feedback_inject_failed", profile_type="monthly", error=str(e))

    profile_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="月画像生成",
    )

    # Quality refinement loop
    source_materials = f"本月时间线事件摘要：{events_text[:500]}\n周画像摘要：{chr(10).join(weekly_texts[:4])}"
    profile_text = await _refine_profile_with_loop(profile_text, source_materials, "monthly")

    await asyncio.to_thread(
        _write_monthly_profile,
        slug,
        f"月画像 {now.strftime('%Y年%m月')}",
        profile_text,
        f"本月画像：{now.strftime('%Y年%m月')}",
    )

    await append_wiki_log("profile", f"生成月画像 {slug}")

    # Cross-profile consistency check (replaces simple lint)
    try:
        from app.services.consistency_checker import check_cross_profile_consistency
        cross_check = await check_cross_profile_consistency(profile_text, "monthly")
        if cross_check.has_conflict:
            change_entries = [f"[跨画像矛盾] {c.conflict_description}" for c in cross_check.conflicts]
            await update_profile_changes(change_entries)
            await _record_conflicts(slug, cross_check)
    except Exception as e:
        logger.error("cross_profile_consistency_failed", profile_type="monthly", error=str(e))

    return {"status": "completed", "slug": slug}


async def generate_overall_profile(strategy: str = "time_weighted") -> dict:
    """Generate an overall profile summarizing all time patterns and traits.

    Strategy options:
    - "time_weighted": 三层时间尺度加权融合（渐进式遗忘）
    - "recursive": 分层递归总结（年画像→终生画像）
    - "dual_track": 双轨制——静态核心档案 + 动态近期画像

    Default is "time_weighted".
    """
    from datetime import datetime, timedelta
    from app.utils.llm import reset_token_counter, get_token_count

    reset_token_counter()
    now = datetime.now()
    slug = "overall_profile"

    # Common data collection
    monthly_profiles = await asyncio.to_thread(_read_monthly_profiles_recent, 6)
    all_monthly_profiles = await asyncio.to_thread(_read_monthly_profiles)
    entities = await asyncio.to_thread(_read_self_entity_summaries, 90)
    changes_text = await asyncio.to_thread(_read_profile_changes_truth)

    # Read recent 90 days of timeline events as supplementary input
    recent_start = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_end = now.strftime("%Y-%m-%d")
    recent_events = await asyncio.to_thread(_read_timeline_events_by_date_range, recent_start, recent_end, 300)
    recent_events_text = _format_timeline_events(recent_events, max_count=40)

    monthly_texts = [mp["compiled_truth"] for mp in monthly_profiles if mp["compiled_truth"]]
    all_monthly_texts = [mp["compiled_truth"] for mp in all_monthly_profiles if mp["compiled_truth"]]

    entity_summaries = []
    for e in entities:
        fm = {}
        try:
            fm = json.loads(e["frontmatter"]) if e["frontmatter"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        confidence = fm.get("confidence", fm.get("evidence_strength", ""))
        entity_summaries.append(f"- {e['title']}({e['type']}): {e['summary'] or '无摘要'}" + (f" 置信度:{confidence}" if confidence else ""))

    # Build prompt based on strategy
    strategy_labels = {
        "time_weighted": "三层时间尺度加权融合",
        "recursive": "分层递归总结",
        "dual_track": "双轨制（静态核心+动态近期）",
    }
    strategy_label = strategy_labels.get(strategy, "三层时间尺度加权融合")

    if strategy == "time_weighted":
        # Strategy 1: Time-weighted fusion with decay
        # Categorize monthly profiles by recency
        recent_months = monthly_texts[:3]  # 最近3个月
        mid_months = monthly_texts[3:6] if len(monthly_texts) > 3 else []
        long_months = all_monthly_texts[6:] if len(all_monthly_texts) > 6 else []

        prompt = f"""请根据以下数据撰写总画像（截至{now.strftime('%Y年%m月%d日')}），使用「三层时间尺度加权融合」策略。

## 数据来源（按时间权重排列）

### 近期数据（权重1.0，最近3个月月画像）：
{chr(10).join(recent_months) if recent_months else '暂无'}

### 中期数据（权重0.5，4-6个月前月画像）：
{chr(10).join(mid_months) if mid_months else '暂无'}

### 长期数据（权重0.2，6个月前月画像摘要）：
{chr(10).join(long_months[:6]) if long_months else '暂无'}

### 近90天时间线事件（权重0.9，共{len(recent_events)}条）：
{recent_events_text if recent_events_text else '暂无'}

### 变化记录（权重0.6）：
{changes_text[:1500] if changes_text else '暂无'}

### 自我相关实体（权重0.8）：
{chr(10).join(entity_summaries[:30])}

请按照时间权重融合以上数据，撰写总画像，包含：
1. 核心人格特质：最稳定的性格特征（优先从长期数据提取）
2. 行为模式：长期稳定的行为习惯及其近期变化趋势
3. 价值观体系：核心价值观和信念
4. 成长轨迹：长期的变化趋势，标注关键转折点
5. 近期变化：最近3个月的显著变化
6. 未来展望：基于当前趋势的发展预测

注意：近期数据更详细但可能只是短期波动，长期数据虽模糊但反映稳定特质。请合理权衡。
请用中文撰写，客观深入，400-600字。"""

    elif strategy == "recursive":
        # Strategy 3: Recursive yearly → lifetime summary
        # Read all monthly profiles grouped by year
        all_profiles = await asyncio.to_thread(_read_all_monthly_profiles_grouped_by_year)

        yearly_sections = []
        for year, profiles in sorted(all_profiles.items(), reverse=True):
            texts = [p["compiled_truth"] for p in profiles if p.get("compiled_truth")]
            if texts:
                yearly_sections.append(f"### {year}年月画像摘要：\n{chr(10).join(texts[:12])}")

        prompt = f"""请根据以下数据撰写总画像（截至{now.strftime('%Y年%m月%d日')}），使用「分层递归总结」策略。

## 各年度画像数据
{chr(10).join(yearly_sections) if yearly_sections else '暂无月画像数据'}

## 近90天时间线事件（共{len(recent_events)}条）
{recent_events_text if recent_events_text else '暂无'}

## 跨年变化记录
{changes_text[:2000] if changes_text else '暂无'}

## 自我相关实体
{chr(10).join(entity_summaries[:30])}

请从各年度数据中提炼出：
1. **核心人格的连续性**：哪些特质在各年度始终稳定？
2. **关键转折点**：哪些年份出现了显著变化？变化是什么？
3. **成长轨迹**：长期发展趋势是什么？
4. **周期性模式**：是否存在季节性或周期性行为模式？
5. **当前阶段**：用户目前处于什么样的人生阶段？
6. **未来展望**：基于历史趋势的发展预测

请用中文撰写，客观深入，400-600字。"""

    elif strategy == "dual_track":
        # Strategy 4: Dual-track: static core + dynamic recent
        prompt = f"""请根据以下数据撰写总画像（截至{now.strftime('%Y年%m月%d日')}），使用「双轨制」策略。

## 数据来源

全部月画像摘要：
{chr(10).join(all_monthly_texts[:12]) if all_monthly_texts else '暂无'}

近90天时间线事件（共{len(recent_events)}条）：
{recent_events_text if recent_events_text else '暂无'}

自我相关实体摘要：
{chr(10).join(entity_summaries[:30])}

画像变化记录：
{changes_text[:2000] if changes_text else '暂无'}

请将总画像分为两个独立部分：

### 第一部分：静态核心档案
提炼用户一生几乎不变的特质（如早年形成的价值观、基本性格倾向），这些特质跨越所有时间窗口始终稳定。
格式：每个特质一行，包含特质名称、描述、证据来源。

### 第二部分：动态近期画像
描述最近3-6个月的显著变化趋势，包括新习惯形成、旧习惯消退、关系变化、情绪模式变化等。

### 第三部分：融合叙述
将以上两部分融合成一段连贯的文字（200字左右），让用户同时看到"我是谁"和"我正在变成谁"。

请用中文撰写，客观深入。"""

    else:
        # Fallback to time_weighted
        prompt = f"""请根据以下数据撰写总画像（截至{now.strftime('%Y年%m月%d日')}）。

月画像摘要（最近6个月）：
{chr(10).join(monthly_texts[:6])}

近90天时间线事件（共{len(recent_events)}条）：
{recent_events_text if recent_events_text else '暂无'}

自我相关实体摘要（习惯/情绪模式/价值观信号）：
{chr(10).join(entity_summaries[:30])}

画像变化记录：
{changes_text[:1500] if changes_text else '暂无'}

请撰写总画像，包含：
1. 核心人格特质：最稳定的性格特征
2. 行为模式：长期稳定的行为习惯
3. 价值观体系：核心价值观和信念
4. 成长轨迹：长期的变化趋势
5. 潜在风险：需要关注的心理或行为模式
6. 未来展望：基于当前趋势的发展预测

注意：总画像应聚焦于用户自身的性格特质和行为模式，不要混入他人的信息。
请用中文撰写，客观深入，400-600字。"""

    # Inject user feedback constraints
    try:
        from app.services.feedback_service import build_feedback_prompt_section
        feedback_section = await build_feedback_prompt_section("overall_profile", f"总画像({strategy_label}) 截至{now.strftime('%Y年%m月')}")
        if feedback_section:
            prompt += f"\n\n{feedback_section}"
    except Exception as e:
        logger.error("feedback_inject_failed", profile_type="overall", error=str(e))

    profile_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose=f"总画像生成({strategy_label})",
    )

    # Quality refinement loop
    source_materials = f"月画像摘要：{chr(10).join(monthly_texts[:6])}\n近90天时间线事件摘要：{recent_events_text[:500]}\n自我实体摘要：{chr(10).join(entity_summaries[:15])}"
    profile_text = await _refine_profile_with_loop(profile_text, source_materials, "overall")

    await asyncio.to_thread(
        _write_monthly_profile,
        slug,
        f"总画像·{strategy_label}（截至{now.strftime('%Y-%m-%d')}）",
        profile_text,
        f"总画像({strategy_label})：截至{now.strftime('%Y年%m月')}",
    )

    await append_wiki_log("profile", f"生成总画像({strategy_label}) {slug}")

    # Cross-profile consistency check (replaces simple lint)
    try:
        from app.services.consistency_checker import check_cross_profile_consistency
        cross_check = await check_cross_profile_consistency(profile_text, "overall")
        if cross_check.has_conflict:
            change_entries = [f"[跨画像矛盾] {c.conflict_description}" for c in cross_check.conflicts]
            await update_profile_changes(change_entries)
            await _record_conflicts(slug, cross_check)
    except Exception as e:
        logger.error("cross_profile_consistency_failed", profile_type="overall", error=str(e))

    # Log token usage
    total_tokens = get_token_count()
    _log_portrait_token(f"总画像({strategy_label})", total_tokens)

    return {"status": "completed", "slug": slug, "strategy": strategy, "strategy_label": strategy_label}


def _read_monthly_profiles() -> list[dict]:
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, slug FROM pages WHERE type = 'system' AND slug LIKE 'monthly_profile_%' AND compiled_truth != ''",
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_all_monthly_profiles_grouped_by_year() -> dict[str, list[dict]]:
    """Read all monthly profiles grouped by year."""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, slug FROM pages WHERE type = 'system' AND slug LIKE 'monthly_profile_%' AND compiled_truth != '' ORDER BY slug",
    )
    rows = [dict(row) for row in cursor.fetchall()]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        # slug format: monthly_profile_YYYYMM
        slug = row.get("slug", "")
        try:
            year = slug.split("_")[-1][:4]
        except (IndexError, ValueError):
            year = "unknown"
        grouped.setdefault(year, []).append(row)
    return grouped


def _read_monthly_profiles_recent(months: int = 6) -> list[dict]:
    """Read monthly profiles from the last N months, ordered by slug DESC (most recent first)."""
    from datetime import datetime, timedelta

    db = get_compile_sync_connection()
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y%m")
    cursor = db.execute(
        "SELECT compiled_truth FROM pages WHERE type = 'system' "
        "AND slug LIKE 'monthly_profile_%' AND compiled_truth != '' "
        "AND slug >= ? ORDER BY slug DESC",
        (f"monthly_profile_{cutoff}",),
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_monthly_profiles_for_year(year: int) -> list[dict]:
    """Read all monthly profiles for a specific year, ordered by slug DESC."""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth FROM pages WHERE type = 'system' "
        "AND slug LIKE ? AND compiled_truth != '' ORDER BY slug DESC",
        (f"monthly_profile_{year}%",),
    )
    return [dict(row) for row in cursor.fetchall()]


def _log_portrait_token(portrait_type: str, token_count: int) -> None:
    """Append portrait token usage to the log file."""
    from pathlib import Path
    from datetime import datetime
    try:
        log_file = Path(__file__).resolve().parent.parent.parent / "data" / "token_usage.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{now}] 生成{portrait_type}，消耗了{token_count}token\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pre-aggregation layer: monthly_memory & yearly_memory
# ---------------------------------------------------------------------------

def _read_monthly_events(year_month: str) -> list[dict]:
    """读取指定月份的 timeline_events，用于月度记忆生成。

    Args:
        year_month: 格式 YYYYMM，如 "202606"
    """
    from datetime import datetime

    db = get_compile_sync_connection()
    # 解析年月
    year = int(year_month[:4])
    month = int(year_month[4:6])
    start_date = f"{year}-{month:02d}-01"
    # 计算下月1号
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    cursor = db.execute(
        "SELECT timestamp, event_type, summary, sentiment, emotional_keywords, related_contacts "
        "FROM timeline_events WHERE timestamp >= ? AND timestamp < ? "
        "ORDER BY timestamp DESC LIMIT 500",
        (start_date, end_date),
    )
    return [dict(row) for row in cursor.fetchall()]


def _write_memory_page(slug: str, title: str, content: str, frontmatter: dict) -> None:
    """写入记忆页面到 pages 表，保存版本历史。"""
    import json as _json

    db = get_compile_sync_connection()
    fm_str = _json.dumps(frontmatter, ensure_ascii=False) if frontmatter else "{}"

    # 检查是否已存在，保存版本历史
    existing = db.execute(
        "SELECT id, compiled_truth FROM pages WHERE slug = ?", (slug,)
    ).fetchone()
    if existing and existing["compiled_truth"]:
        ver_count = db.execute(
            "SELECT COUNT(*) as cnt FROM page_versions WHERE page_id = ?", (existing["id"],)
        ).fetchone()["cnt"]
        db.execute(
            "INSERT INTO page_versions (page_id, version_number, compiled_truth_snapshot, timeline_snapshot) "
            "VALUES (?, ?, ?, '[]')",
            (existing["id"], ver_count + 1, existing["compiled_truth"]),
        )

    db.execute(
        "INSERT OR REPLACE INTO pages (slug, type, title, compiled_truth, summary, timeline, frontmatter, updated_at) "
        "VALUES (?, 'system', ?, ?, ?, '[]', ?, datetime('now','localtime'))",
        (slug, title, content, title, fm_str),
    )
    db.commit()


def _read_monthly_memories(months: int = 12) -> list[dict]:
    """读取最近N个月的 monthly_memory 页面，按 slug DESC 排序。"""
    from datetime import datetime, timedelta

    db = get_compile_sync_connection()
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y%m")
    cursor = db.execute(
        "SELECT compiled_truth, slug, frontmatter FROM pages WHERE type = 'system' "
        "AND slug LIKE 'monthly_memory_%' AND compiled_truth != '' "
        "AND slug >= ? ORDER BY slug DESC",
        (f"monthly_memory_{cutoff}",),
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_all_monthly_memories() -> list[dict]:
    """读取全部月度记忆，按 slug DESC 排序。"""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, slug, frontmatter FROM pages WHERE type = 'system' "
        "AND slug LIKE 'monthly_memory_%' AND compiled_truth != '' "
        "ORDER BY slug DESC",
    )
    return [dict(row) for row in cursor.fetchall()]


def _read_yearly_memories() -> list[dict]:
    """读取全部年度记忆，按 slug DESC 排序。"""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, slug FROM pages WHERE type = 'system' "
        "AND slug LIKE 'yearly_memory_%' AND compiled_truth != '' "
        "ORDER BY slug DESC",
    )
    return [dict(row) for row in cursor.fetchall()]


async def generate_monthly_memory(year_month: str | None = None) -> dict:
    """生成月度记忆：从上月事件中提炼约300字摘要 + JSON统计特征。

    Args:
        year_month: 格式 YYYYMM，默认为上月

    存储位置: pages 表，slug = monthly_memory_YYYYMM，type='system'
    """
    from datetime import datetime, timedelta

    now = datetime.now()
    if year_month is None:
        # 默认为上月
        first_of_this_month = now.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        year_month = last_month_end.strftime("%Y%m")

    slug = f"monthly_memory_{year_month}"
    year = int(year_month[:4])
    month = int(year_month[4:6])

    # 读取该月的 timeline_events
    events = await asyncio.to_thread(_read_monthly_events, year_month)

    if not events:
        logger.warning("monthly_memory_no_events", year_month=year_month)
        return {"status": "skipped", "reason": f"{year_month}月无事件数据"}

    # 读取该月已有的月度记忆（增量更新）
    db = get_compile_sync_connection()
    existing_row = db.execute(
        "SELECT compiled_truth FROM pages WHERE slug = ?", (slug,)
    ).fetchone()
    existing_memory = dict(existing_row)["compiled_truth"] if existing_row else ""

    # 构建事件文本
    event_texts = []
    for ev in events:
        text = f"[{ev.get('timestamp', '')}] {ev.get('event_type', '')}: {ev.get('summary', '')}"
        if ev.get('sentiment'):
            text += f" (情绪: {ev['sentiment']})"
        if ev.get('emotional_keywords'):
            text += f" [关键词: {ev['emotional_keywords']}]"
        event_texts.append(text)

    # 计算统计特征
    event_types: dict[str, int] = {}
    sentiments: list[float] = []
    for ev in events:
        et = ev.get("event_type", "unknown")
        event_types[et] = event_types.get(et, 0) + 1
        if ev.get("sentiment"):
            try:
                sentiments.append(float(ev["sentiment"]))
            except (ValueError, TypeError):
                pass

    stats = {
        "event_count": len(events),
        "event_type_distribution": event_types,
        "avg_sentiment": round(sum(sentiments) / len(sentiments), 2) if sentiments else None,
        "first_event": events[-1].get("timestamp", "") if events else "",
        "last_event": events[0].get("timestamp", "") if events else "",
    }

    existing_section = ""
    if existing_memory:
        existing_section = f"\n\n已有的月度记忆（请在此基础上增量更新）：\n{existing_memory}"

    prompt = f"""请根据以下{year}年{month}月的事件数据，生成月度记忆摘要。

本月事件（共{len(events)}条）：
{chr(10).join(event_texts[:200])}
{existing_section}

请生成约300字的月度记忆摘要，包含：
1. 习惯频次：本月重复出现的行为及其频率
2. 消费总额/趋势：如有消费相关事件
3. 社交活跃度：与人互动的频率和模式
4. 主要情绪：本月的情绪基调和波动
5. 新习惯/消退习惯：与之前相比的变化

请用中文撰写，客观简洁。"""

    memory_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="月度记忆生成",
    )

    await asyncio.to_thread(
        _write_memory_page,
        slug,
        f"月度记忆 {year}年{month}月",
        memory_text,
        stats,
    )

    await append_wiki_log("profile", f"生成月度记忆 {slug}")

    logger.info("monthly_memory_generated", slug=slug, event_count=len(events))
    return {"status": "completed", "slug": slug, "stats": stats}


async def generate_yearly_memory(year: int | None = None) -> dict:
    """生成年度记忆：从12个月的月度记忆中提炼约500字年度画像。

    Args:
        year: 年份，默认为去年

    存储位置: pages 表，slug = yearly_memory_YYYY，type='system'
    """
    from datetime import datetime

    now = datetime.now()
    if year is None:
        year = now.year - 1

    slug = f"yearly_memory_{year}"

    # 读取该年12个月的 monthly_memory
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, slug FROM pages WHERE type = 'system' "
        "AND slug LIKE ? AND compiled_truth != '' ORDER BY slug ASC",
        (f"monthly_memory_{year}%",),
    )
    monthly_memories = [dict(row) for row in cursor.fetchall()]

    if not monthly_memories:
        logger.warning("yearly_memory_no_data", year=year)
        return {"status": "skipped", "reason": f"{year}年无月度记忆数据"}

    memory_texts = [mm["compiled_truth"] for mm in monthly_memories if mm["compiled_truth"]]

    prompt = f"""请根据以下{year}年1-12月的月度记忆，生成年度画像。

{year}年月度记忆（共{len(memory_texts)}个月）：
{chr(10).join(memory_texts)}

请生成约500字的年度画像，包含：
1. 年度核心事件：对全年影响最大的事件
2. 习惯稳定趋势：哪些习惯全年保持稳定，哪些有变化
3. 价值观变化：价值观层面的演变
4. 情绪年度基调：全年的情绪底色
5. 成长与反思：全年的成长轨迹

请用中文撰写，客观深入。"""

    memory_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="年度记忆生成",
    )

    await asyncio.to_thread(
        _write_memory_page,
        slug,
        f"年度记忆 {year}",
        memory_text,
        {"month_count": len(memory_texts), "year": year},
    )

    await append_wiki_log("profile", f"生成年度记忆 {slug}")

    logger.info("yearly_memory_generated", slug=slug, month_count=len(memory_texts))
    return {"status": "completed", "slug": slug}


# ---------------------------------------------------------------------------
# Synchronous DB helpers for yearly / core / recent profile generation
# ---------------------------------------------------------------------------

def _read_yearly_profiles() -> list[dict]:
    """Read all yearly profiles, ordered by slug DESC (most recent first)."""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth FROM pages WHERE type = 'system' "
        "AND slug LIKE 'yearly_profile_%' AND compiled_truth != '' "
        "ORDER BY slug DESC",
    )
    return [dict(row) for row in cursor.fetchall()]


async def generate_yearly_profile(year: int | None = None) -> dict:
    """Generate a yearly profile summarizing the year's patterns and evolution."""
    from datetime import datetime

    now = datetime.now()
    if year is None:
        year = now.year
    slug = f"yearly_profile_{year}"

    # Read monthly profiles for the specified year
    monthly_profiles = await asyncio.to_thread(_read_monthly_profiles_for_year, year)

    # Read profile changes
    changes_text = await asyncio.to_thread(_read_profile_changes_truth)

    # Read yearly timeline events as additional input (Jan 1 to Dec 31)
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"
    yearly_events = await asyncio.to_thread(_read_timeline_events_by_date_range, year_start, year_end, 500)
    yearly_events_text = _format_timeline_events(yearly_events, max_count=60)

    monthly_texts = [mp["compiled_truth"] for mp in monthly_profiles if mp["compiled_truth"]]

    prompt = f"""请根据以下数据撰写{year}年度画像。

{year}年月画像（共{len(monthly_texts)}个月）：
{chr(10).join(monthly_texts[:12])}

{year}年时间线事件（共{len(yearly_events)}条）：
{yearly_events_text if yearly_events_text else '暂无'}

年度画像变化记录：
{changes_text[:2000] if changes_text else '暂无'}

请撰写年度画像，包含：
1. 年度主题：用一句话概括这一年的核心主题
2. 行为模式演变：全年行为习惯的变化轨迹
3. 关系网络变化：人际关系的重要变化和发展
4. 价值观发展：价值观层面的变化和深化
5. 年度转折点：对全年影响最大的关键事件或时刻
6. 对下一年的展望：基于今年的趋势，对明年的预测和期望

请用中文撰写，客观深入，500-800字。"""

    # Inject user feedback constraints
    try:
        from app.services.feedback_service import build_feedback_prompt_section
        feedback_section = await build_feedback_prompt_section("yearly_profile", f"年画像 {year}")
        if feedback_section:
            prompt += f"\n\n{feedback_section}"
    except Exception as e:
        logger.error("feedback_inject_failed", profile_type="yearly", error=str(e))

    profile_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="年画像生成",
    )

    # Quality refinement loop
    source_materials = f"月画像（{len(monthly_texts)}个月）：{chr(10).join(monthly_texts[:6])}\n年度时间线事件摘要：{yearly_events_text[:500]}"
    profile_text = await _refine_profile_with_loop(profile_text, source_materials, "yearly")

    await asyncio.to_thread(
        _write_monthly_profile,
        slug,
        f"年画像 {year}",
        profile_text,
        f"{year}年度画像",
    )

    await append_wiki_log("profile", f"生成年画像 {slug}")

    return {"status": "completed", "slug": slug}


async def generate_core_personality() -> dict:
    """Generate the core personality profile (static core of the dual-track model).

    Distills traits that remain nearly unchanged throughout life — values and
    personality tendencies formed early on.
    """
    from datetime import datetime

    now = datetime.now()
    slug = "core_personality"

    # Read all monthly profiles
    monthly_profiles = await asyncio.to_thread(_read_monthly_profiles)

    # Read all yearly profiles
    yearly_profiles = await asyncio.to_thread(_read_yearly_profiles)

    # Read profile changes
    changes_text = await asyncio.to_thread(_read_profile_changes_truth)

    # Read a sample of important timeline events (milestones + high importance) as supplementary input
    important_events = await asyncio.to_thread(_read_important_timeline_events, 50)
    important_events_text = _format_timeline_events(important_events, max_count=30)

    monthly_texts = [mp["compiled_truth"] for mp in monthly_profiles if mp["compiled_truth"]]
    yearly_texts = [yp["compiled_truth"] for yp in yearly_profiles if yp["compiled_truth"]]

    prompt = f"""请根据以下历史数据提炼核心人格档案。

全部月画像（共{len(monthly_texts)}个月）：
{chr(10).join(monthly_texts[:24])}

全部年画像（共{len(yearly_texts)}年）：
{chr(10).join(yearly_texts[:10])}

关键时间线事件（里程碑与高重要性事件，共{len(important_events)}条）：
{important_events_text if important_events_text else '暂无'}

画像变化记录：
{changes_text[:2000] if changes_text else '暂无'}

请提炼一生几乎不变的特质，包含：
1. 早年形成的价值观：从成长经历中沉淀的核心信念
2. 基本性格倾向：内向/外向、理性/感性等稳定的性格维度
3. 核心动机：驱动行为的最深层需求
4. 稳定的认知模式：看待世界和问题的基本方式
5. 人际关系基本模式：与人交往的稳定倾向

注意：只提炼那些在长时间跨度中反复出现、几乎不变的特质，不要包含短期波动或近期变化。
请用中文撰写，客观深刻，400-600字。"""

    # Inject user feedback constraints
    try:
        from app.services.feedback_service import build_feedback_prompt_section
        feedback_section = await build_feedback_prompt_section("core_personality", "核心人格档案")
        if feedback_section:
            prompt += f"\n\n{feedback_section}"
    except Exception as e:
        logger.error("feedback_inject_failed", profile_type="core", error=str(e))

    profile_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="核心人格生成",
    )

    # Quality refinement loop
    source_materials = f"月画像（{len(monthly_texts)}个月）：{chr(10).join(monthly_texts[:6])}\n年画像（{len(yearly_texts)}年）：{chr(10).join(yearly_texts[:3])}\n关键时间线事件摘要：{important_events_text[:500]}"
    profile_text = await _refine_profile_with_loop(profile_text, source_materials, "core")

    await asyncio.to_thread(
        _write_monthly_profile,
        slug,
        f"核心人格档案（截至{now.strftime('%Y-%m-%d')}）",
        profile_text,
        "核心人格档案",
    )

    await append_wiki_log("profile", f"生成核心人格档案 {slug}")

    return {"status": "completed", "slug": slug}


async def generate_recent_dynamics() -> dict:
    """Generate the recent dynamics profile (dynamic track of the dual-track model).

    Captures recent change trends based on the last 3 months of monthly
    profiles and the last 90 days of timeline events.
    """
    from datetime import datetime, timedelta

    now = datetime.now()
    slug = f"recent_dynamics_{now.strftime('%Y%m')}"

    # Read recent 3 monthly profiles
    monthly_profiles = await asyncio.to_thread(_read_monthly_profiles_recent, 3)

    # Read recent 90 days of timeline events as the PRIMARY input
    recent_start = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_end = now.strftime("%Y-%m-%d")
    recent_events = await asyncio.to_thread(_read_timeline_events_by_date_range, recent_start, recent_end, 500)
    recent_events_text = _format_timeline_events(recent_events, max_count=60)

    monthly_texts = [mp["compiled_truth"] for mp in monthly_profiles if mp["compiled_truth"]]

    prompt = f"""请根据以下数据撰写近期动态画像（截至{now.strftime('%Y年%m月%d日')}）。

最近90天时间线事件（共{len(recent_events)}条）：
{recent_events_text if recent_events_text else '暂无'}

最近3个月月画像：
{chr(10).join(monthly_texts[:3])}

请撰写近期动态画像，包含：
1. 近期行为变化趋势：哪些行为在增加/减少
2. 情绪波动模式：近期情绪的起伏和触发因素
3. 习惯养成与消退：正在形成或正在消退的习惯
4. 价值观信号变化：近期体现出的价值观倾向变化
5. 关系动态：近期人际关系的重要变化
6. 需要关注的信号：可能预示重要变化的早期迹象

请用中文撰写，客观敏锐，300-500字。"""

    # Inject user feedback constraints
    try:
        from app.services.feedback_service import build_feedback_prompt_section
        feedback_section = await build_feedback_prompt_section("recent_dynamics", f"近期动态画像 {now.strftime('%Y年%m月')}")
        if feedback_section:
            prompt += f"\n\n{feedback_section}"
    except Exception as e:
        logger.error("feedback_inject_failed", profile_type="recent", error=str(e))

    profile_text = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="近期动态生成",
    )

    # Quality refinement loop
    source_materials = f"近90天时间线事件摘要：{recent_events_text[:500]}\n月画像：{chr(10).join(monthly_texts[:3])}"
    profile_text = await _refine_profile_with_loop(profile_text, source_materials, "recent")

    await asyncio.to_thread(
        _write_monthly_profile,
        slug,
        f"近期动态画像（{now.strftime('%Y年%m月')}）",
        profile_text,
        f"近期动态：{now.strftime('%Y年%m月')}",
    )

    await append_wiki_log("profile", f"生成近期动态画像 {slug}")

    return {"status": "completed", "slug": slug}
