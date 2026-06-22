from __future__ import annotations

import asyncio
import math

import structlog

from app.database import get_connection
from app.services.vector_store import vector_store
from app.utils.embedding import embed_texts

logger = structlog.get_logger()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _distance_to_similarity(distance: float) -> float:
    """LanceDB 返回的 _distance 是 L2 距离的平方，转为 0-1 的相似度（越大越相似）。

    LanceDB 默认使用 L2 距离，distance 范围 [0, +∞)。
    用 1 / (1 + distance) 转为 (0, 1] 的相似度。
    """
    try:
        d = float(distance)
        return 1.0 / (1.0 + d) if d >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


class HybridRAG:
    """两路 RAG 检索：时间线向量检索 + 日记原文向量检索。

    画像检索已移除（画像由 snapshot 快照层注入，RAG 不再重复检索）。
    保留类名 HybridRAG 以保持向后兼容。
    """

    # 时间线向量检索 top-K
    TIMELINE_TOP_K = 10
    # 时间线相似度阈值（基于 LanceDB _distance 转换的相似度）
    TIMELINE_MIN_SIMILARITY = 0.3
    # 命中事件前后窗口（每侧）
    TIMELINE_WINDOW = 7
    # 时间线上下文最大条数
    TIMELINE_MAX_CONTEXT = 15
    # 原文向量检索 top-K
    DIARY_TOP_K = 5
    # 日记相似度阈值
    DIARY_MIN_SIMILARITY = 0.3
    # 日记原文展示最大长度
    DIARY_CONTENT_MAX_LEN = 500

    async def retrieve(
        self,
        query: str,
        context: dict = None,
        mentioned_contacts: list[str] = None,
        limit: int = 10,
        query_vector: list[float] = None,
    ) -> dict:
        """两路并行 RAG 检索。

        参数:
            query: 用户查询文本
            query_vector: 预计算的 query embedding（可选，避免重复调用 embedding API）

        返回:
            {
                "timeline_context": "时间线上下文文本",
                "diary_context": "日记原文上下文文本",
                "sources": [...],             # 检索来源信息
            }
        """
        if query_vector is None:
            query_vector = (await embed_texts([query]))[0]

        timeline_result, diary_result = await asyncio.gather(
            self._retrieve_timeline(query, query_vector),
            self._retrieve_text_content(query, query_vector),
            return_exceptions=True,
        )

        timeline_context = ""
        diary_context = ""
        sources: list = []

        if isinstance(timeline_result, Exception):
            logger.error("时间线检索失败", error=str(timeline_result), exc_info=True)
        else:
            timeline_context = timeline_result.get("context", "")
            sources.extend(timeline_result.get("sources", []))

        if isinstance(diary_result, Exception):
            logger.error("原文检索失败", error=str(diary_result), exc_info=True)
        else:
            diary_context = diary_result.get("context", "")
            sources.extend(diary_result.get("sources", []))

        logger.info(
            "rag_retrieve_done",
            timeline_hits=sum(1 for s in sources if s.get("type") == "timeline"),
            diary_hits=sum(1 for s in sources if s.get("type") == "diary"),
        )

        return {
            "timeline_context": timeline_context,
            "diary_context": diary_context,
            "sources": sources,
        }

    async def _retrieve_timeline(
        self, query: str, query_vector: list[float]
    ) -> dict:
        """时间线向量检索：在 LanceDB timeline 表中检索语义相关的事件。

        检索流程：
        1. LanceDB 向量检索 top-K（全量候选，无时间偏差）
        2. 按相似度阈值过滤
        3. 用命中事件的 timestamp 回 SQLite 查询前后窗口事件
        4. 构建上下文（summary + content 完整展示）
        """
        try:
            # 1. LanceDB 向量检索
            results = await vector_store.search_timeline(
                query_vector, limit=self.TIMELINE_TOP_K
            )
            if not results:
                return {"context": "", "sources": []}

            # 2. 按相似度阈值过滤
            hits = []
            for r in results:
                similarity = _distance_to_similarity(r.get("_distance", 1.0))
                if similarity >= self.TIMELINE_MIN_SIMILARITY:
                    r["_similarity"] = similarity
                    hits.append(r)

            if not hits:
                return {"context": "", "sources": []}

            # 3. 回 SQLite 查询命中事件的完整字段 + 前后窗口事件
            hit_ids = [h["id"] for h in hits]
            hit_timestamps = [h.get("timestamp", "") for h in hits if h.get("timestamp")]
            if not hit_timestamps:
                return {"context": "", "sources": []}

            min_ts = min(hit_timestamps)
            max_ts = max(hit_timestamps)

            # 查询命中事件 + 时间窗口内的事件
            # 通过 timestamp 范围扩展候选，再按 timestamp 排序
            async with get_connection() as db:
                # 先取命中事件的完整字段
                placeholders = ",".join("?" * len(hit_ids))
                cursor = await db.execute(
                    f"""
                    SELECT id, timestamp, event_type, summary, content,
                           sentiment, importance_score, source_type, source_id
                    FROM timeline_events
                    WHERE id IN ({placeholders})
                    """,
                    hit_ids,
                )
                hit_events = [dict(row) for row in await cursor.fetchall()]

                if not hit_events:
                    return {"context": "", "sources": []}

                # 查询时间窗口内的事件（用于上下文扩展）
                cursor = await db.execute(
                    """
                    SELECT id, timestamp, event_type, summary, content,
                           sentiment, importance_score, source_type, source_id
                    FROM timeline_events
                    WHERE timestamp BETWEEN ? AND ?
                    ORDER BY timestamp
                    """,
                    (min_ts, max_ts),
                )
                window_events = [dict(row) for row in await cursor.fetchall()]

            # 4. 构建上下文
            # 如果窗口事件太少（< TIMELINE_MAX_CONTEXT），用命中事件附近的事件补充
            hit_id_set = {e["id"] for e in hit_events}
            if len(window_events) < self.TIMELINE_MAX_CONTEXT:
                # 查询命中事件前后各 TIMELINE_WINDOW 条
                async with get_connection() as db:
                    cursor = await db.execute(
                        """
                        SELECT id, timestamp, event_type, summary, content,
                               sentiment, importance_score, source_type, source_id
                        FROM timeline_events
                        ORDER BY timestamp
                        """
                    )
                    all_events = [dict(row) for row in await cursor.fetchall()]

                # 找到命中事件在全局列表中的位置，取前后窗口
                nearby_events = []
                nearby_ids = set()
                for hit in hit_events:
                    hit_idx = next(
                        (i for i, e in enumerate(all_events) if e["id"] == hit["id"]),
                        None,
                    )
                    if hit_idx is None:
                        continue
                    start = max(0, hit_idx - self.TIMELINE_WINDOW)
                    end = min(len(all_events), hit_idx + self.TIMELINE_WINDOW + 1)
                    for e in all_events[start:end]:
                        if e["id"] not in nearby_ids:
                            nearby_ids.add(e["id"])
                            nearby_events.append(e)

                # 合并窗口事件和附近事件
                all_context_events = window_events + [
                    e for e in nearby_events if e["id"] not in {we["id"] for we in window_events}
                ]
            else:
                all_context_events = window_events

            # 按时间排序，截取最多 TIMELINE_MAX_CONTEXT 条
            all_context_events.sort(key=lambda x: x["timestamp"])
            all_context_events = all_context_events[: self.TIMELINE_MAX_CONTEXT]

            # 构建上下文文本：命中事件展示 summary + content，非命中事件只展示 summary
            context_lines = []
            sources = []
            for e in all_context_events:
                ts = e.get("timestamp", "")
                etype = e.get("event_type", "")
                summary = e.get("summary", "")
                content = e.get("content", "")

                if e["id"] in hit_id_set:
                    # 命中事件：展示完整信息
                    line = f"- [{ts}] [{etype}] {summary}"
                    if content and content != summary:
                        line += f"\n  原文：{content}"
                    context_lines.append(line)
                else:
                    # 窗口事件：只展示 summary
                    context_lines.append(f"- [{ts}] [{etype}] {summary}")

                sources.append({
                    "type": "timeline",
                    "id": e.get("id"),
                    "summary": summary,
                    "timestamp": ts,
                    "source_type": e.get("source_type"),
                    "source_id": e.get("source_id"),
                    "is_hit": e["id"] in hit_id_set,
                })

            return {"context": "\n".join(context_lines), "sources": sources}
        except Exception as e:
            logger.error("时间线检索异常", error=str(e), exc_info=True)
            return {"context": "", "sources": []}

    async def _retrieve_text_content(
        self, query: str, query_vector: list[float]
    ) -> dict:
        """日记原文向量检索：在 LanceDB diaries 表中检索与查询语义相关的日记原文片段。"""
        try:
            results = await vector_store.search_diaries(
                query_vector, limit=self.DIARY_TOP_K
            )
            if not results:
                return {"context": "", "sources": []}

            # 按相似度阈值过滤
            filtered = []
            for r in results:
                similarity = _distance_to_similarity(r.get("_distance", 1.0))
                if similarity >= self.DIARY_MIN_SIMILARITY:
                    r["_similarity"] = similarity
                    filtered.append(r)

            if not filtered:
                return {"context": "", "sources": []}

            context_lines = []
            sources = []
            for r in filtered:
                content = r.get("content", "")
                source_date = r.get("source_date", "")
                source_id = r.get("source_id", "")
                # 不截断或放宽截断到 500 字
                display_content = content[:self.DIARY_CONTENT_MAX_LEN]
                if len(content) > self.DIARY_CONTENT_MAX_LEN:
                    display_content += "..."
                context_lines.append(f"- [{source_date}] {display_content}")
                sources.append({
                    "type": "diary",
                    "source_id": source_id,
                    "source_date": source_date,
                    "content_preview": content[:100],
                    "content_full": content,
                    "similarity": r.get("_similarity", 0),
                })

            return {"context": "\n".join(context_lines), "sources": sources}
        except Exception as e:
            logger.error("原文检索异常", error=str(e), exc_info=True)
            return {"context": "", "sources": []}


hybrid_rag = HybridRAG()
