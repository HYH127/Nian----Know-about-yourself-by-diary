from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog

from app.database import get_connection
from app.models.timeline import TimelineEvent, TimelineEventCreate
from app.prompts.event_extraction import EVENT_EXTRACTION_PROMPT
from app.utils.llm import chat_completion

logger = structlog.get_logger()


async def create_timeline_event(event: TimelineEventCreate) -> TimelineEvent:
    event_id = uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as db:
        await db.execute(
            "INSERT INTO timeline_events "
            "(id, timestamp, event_type, summary, content, sentiment, emotional_keywords, "
            "related_contacts, related_events, related_page_slugs, "
            "source_type, source_id, importance_score, is_milestone, is_confirmed, confirmed_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                event.timestamp,
                event.event_type,
                event.summary,
                event.content,
                event.sentiment,
                event.emotional_keywords,
                event.related_contacts,
                event.related_events,
                event.related_page_slugs,
                event.source_type,
                event.source_id,
                event.importance_score,
                1 if event.is_milestone else 0,
                1 if event.is_confirmed else 0,
                event.confirmed_at,
                now,
            ),
        )
        await db.commit()

    # 同步到向量库（失败仅记日志，不影响主流程）
    try:
        from app.services.vector_store import vector_store
        from app.utils.embedding import embed_texts
        vector = (await embed_texts([event.summary]))[0]
        await vector_store.add_timeline_event(
            event_id=event_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            summary=event.summary,
            content=event.content,
            source_type=event.source_type,
            source_id=event.source_id or "",
            vector=vector,
        )
    except Exception as e:
        logger.warning("timeline_vector_sync_failed", event_id=event_id, error=str(e))

    return TimelineEvent(
        id=event_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        summary=event.summary,
        content=event.content,
        sentiment=event.sentiment,
        emotional_keywords=event.emotional_keywords,
        related_contacts=event.related_contacts,
        related_events=event.related_events,
        related_page_slugs=event.related_page_slugs,
        source_type=event.source_type,
        source_id=event.source_id,
        importance_score=event.importance_score,
        is_milestone=event.is_milestone,
        is_confirmed=event.is_confirmed,
        confirmed_at=event.confirmed_at,
        created_at=now,
    )


def _parse_events_response(raw: str, source_type: str, source_id: str) -> list[TimelineEventCreate]:
    json_str = raw.strip()
    # Try to extract from code fence
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", json_str, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    else:
        # Remove opening code fence if present (unclosed fence = truncated response)
        json_str = re.sub(r'^```(?:json)?\s*\n?', '', json_str)

    try:
        items = json.loads(json_str)
    except json.JSONDecodeError:
        # Try to find a complete JSON array
        array_match = re.search(r"\[.*\]", json_str, re.DOTALL)
        if array_match:
            try:
                items = json.loads(array_match.group())
            except json.JSONDecodeError:
                # Try to fix truncated JSON: find last complete object and close the array
                # Find the last "}" that closes a complete object
                last_brace = json_str.rfind('}')
                if last_brace > 0:
                    truncated = json_str[:last_brace + 1] + ']'
                    # Remove any leading text before the array
                    bracket_pos = truncated.find('[')
                    if bracket_pos >= 0:
                        truncated = truncated[bracket_pos:]
                    try:
                        items = json.loads(truncated)
                    except json.JSONDecodeError:
                        return []
                else:
                    return []
        else:
            return []

    if not isinstance(items, list):
        return []

    events: list[TimelineEventCreate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            events.append(TimelineEventCreate(
                timestamp=item.get("timestamp", ""),
                event_type=item.get("event_type", "routine"),
                summary=item.get("summary", ""),
                content=item.get("evidence", item.get("summary", "")),
                sentiment=item.get("sentiment"),
                emotional_keywords=",".join(item.get("emotional_keywords", []))
                if isinstance(item.get("emotional_keywords"), list)
                else item.get("emotional_keywords"),
                related_contacts=",".join(item.get("related_contacts", []))
                if isinstance(item.get("related_contacts"), list)
                else item.get("related_contacts"),
                related_page_slugs=None,
                importance_score=item.get("importance_score", 0.5),
                is_milestone=item.get("is_milestone", False),
                source_type=source_type,
                source_id=source_id,
            ))
        except Exception:
            continue

    return events


async def extract_and_create_events(
    content: str, source_type: str, source_id: str, source_date: Optional[str] = None,
    context: Optional[str] = None,
) -> list[TimelineEvent]:
    """从内容中提取时间线事件并存储。source_date 用于修正 LLM 提取的错误日期。
    context 为可选的叙事背景文本，用于校准情感打分视角。"""
    prompt = EVENT_EXTRACTION_PROMPT.format(
        content=content,
        source_type=source_type,
        source_id=source_id,
        context=context or "（无叙事背景信息）",
    )
    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=50000,
        purpose="时间线事件提取",
    )

    event_creates = _parse_events_response(raw, source_type, source_id)
    if not event_creates:
        return []

    # Fix timestamps: if source_date is provided, override LLM-extracted dates
    # LLM often extracts wrong years (e.g. 2023 for a 2025 diary)
    if source_date:
        for ec in event_creates:
            ec.timestamp = _fix_event_timestamp(ec.timestamp, source_date)

    # Query existing page slugs for matching
    existing_slugs = await _get_existing_page_slugs()

    events: list[TimelineEvent] = []
    for event_create in event_creates:
        # Match related_page_slugs from related_contacts and summary
        matched_slugs = _match_page_slugs(event_create, existing_slugs)
        event_create.related_page_slugs = ",".join(matched_slugs) if matched_slugs else None
        event = await create_timeline_event(event_create)
        events.append(event)

    return events


def _fix_event_timestamp(event_ts: str, source_date: str) -> str:
    """修正 LLM 提取的事件时间戳。用 source_date (YYYY-MM-DD) 替换事件日期。

    LLM 经常提取错误的年份（如把 2025 年的日记提取为 2023 年事件）。
    保留 LLM 提取的时分秒（如果有），只替换日期部分。
    """
    if not source_date:
        return event_ts

    # source_date should be YYYY-MM-DD
    date_part = source_date[:10]

    # If event_ts has time component (YYYY-MM-DD HH:MM:SS), preserve time
    if event_ts and len(event_ts) > 10:
        time_part = event_ts[10:]  # " HH:MM:SS" or "THH:MM:SS"
        return date_part + time_part

    return date_part


async def _get_existing_page_slugs() -> list[dict]:
    """Get all page slugs and titles for matching."""
    async with get_connection() as db:
        cursor = await db.execute("SELECT slug, title, type FROM pages WHERE type != 'system'")
        return [dict(row) for row in await cursor.fetchall()]


def _match_page_slugs(event: TimelineEventCreate, pages: list[dict]) -> list[str]:
    """Match event to page slugs. Use longest-title-first to avoid substring overlap.
    E.g. "王小波" and "小波" both exist → event mentioning "王小波" matches only "王小波",
    not "小波" (since "小波" is a substring of the already-matched "王小波")."""
    matched = set()
    contacts_str = (event.related_contacts or "").lower()
    summary_str = (event.summary or "").lower()
    content_str = (event.content or "").lower()

    # Sort by title length descending so longer titles (e.g. "王小波") match first
    sorted_pages = sorted(pages, key=lambda p: len(p["title"] or ""), reverse=True)
    matched_titles = set()

    for page in sorted_pages:
        title_lower = (page["title"] or "").lower()
        slug = page["slug"]
        if not title_lower or len(title_lower) < 2:
            continue
        # Skip if any already-matched title contains this shorter title as substring
        # (e.g. "王小波" already matched → skip "小波")
        if any(title_lower in mt for mt in matched_titles if len(mt) > len(title_lower)):
            continue
        if title_lower in contacts_str or title_lower in summary_str or title_lower in content_str:
            matched.add(slug)
            matched_titles.add(title_lower)

    return list(matched)


async def get_timeline_event(event_id: str) -> TimelineEvent | None:
    """获取单个时间线事件"""
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM timeline_events WHERE id = ?",
            (event_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_event(row)


async def list_timeline_events(
    limit: int = 20,
    offset: int = 0,
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    contact: Optional[str] = None,
    min_importance: Optional[float] = None,
) -> list[TimelineEvent]:
    """按条件查询时间线事件列表"""
    conditions = []
    params: list = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if start_date:
        conditions.append("timestamp >= ?")
        params.append(start_date)

    if end_date:
        conditions.append("timestamp <= ?")
        params.append(end_date)

    if contact:
        conditions.append("related_contacts LIKE ?")
        params.append(f"%{contact}%")

    if min_importance is not None:
        conditions.append("importance_score >= ?")
        params.append(min_importance)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = (
        f"SELECT * FROM timeline_events {where_clause} "
        f"ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    async with get_connection() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        events = [_row_to_event(row) for row in rows]

        return events


async def count_timeline_events(
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    contact: Optional[str] = None,
    min_importance: Optional[float] = None,
) -> int:
    """统计符合条件的时时间线事件数量"""
    conditions = []
    params: list = []

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if start_date:
        conditions.append("timestamp >= ?")
        params.append(start_date)

    if end_date:
        conditions.append("timestamp <= ?")
        params.append(end_date)

    if contact:
        conditions.append("related_contacts LIKE ?")
        params.append(f"%{contact}%")

    if min_importance is not None:
        conditions.append("importance_score >= ?")
        params.append(min_importance)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"SELECT COUNT(*) as cnt FROM timeline_events {where_clause}"

    async with get_connection() as db:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


def _row_to_event(row) -> TimelineEvent:
    return TimelineEvent(
        id=row["id"],
        timestamp=row["timestamp"],
        event_type=row["event_type"],
        summary=row["summary"],
        content=row["content"] if "content" in row.keys() else row.get("summary", ""),
        sentiment=row["sentiment"],
        emotional_keywords=row["emotional_keywords"],
        related_contacts=row["related_contacts"],
        related_events=row["related_events"],
        related_page_slugs=row["related_page_slugs"] if "related_page_slugs" in row.keys() else None,
        source_type=row["source_type"],
        source_id=row["source_id"],
        importance_score=row["importance_score"],
        is_milestone=bool(row["is_milestone"]),
        is_confirmed=bool(row["is_confirmed"]) if "is_confirmed" in row.keys() else False,
        confirmed_at=row["confirmed_at"] if "confirmed_at" in row.keys() else None,
        is_locked=bool(row["is_locked"]) if "is_locked" in row.keys() else False,
        locked_at=row["locked_at"] if "locked_at" in row.keys() else None,
        created_at=row["created_at"],
    )


async def fix_diary_event_timestamps() -> int:
    """修正所有 diary 来源事件的时间戳，用对应日记的 date 替换错误的 timestamp。
    返回修正的条目数。"""
    async with get_connection() as db:
        # Find all diary-sourced events and join with diaries to get correct dates
        cursor = await db.execute(
            "SELECT te.id, te.timestamp, d.date "
            "FROM timeline_events te "
            "JOIN diaries d ON te.source_id = d.id "
            "WHERE te.source_type = 'diary' "
            "AND te.source_id IS NOT NULL "
            "AND SUBSTR(te.timestamp, 1, 10) != d.date"
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        count = 0
        for row in rows:
            event_id = row["id"]
            old_ts = row["timestamp"]
            diary_date = row["date"]

            # Preserve time component if present
            new_ts = _fix_event_timestamp(old_ts, diary_date)

            await db.execute(
                "UPDATE timeline_events SET timestamp = ? WHERE id = ?",
                (new_ts, event_id),
            )
            count += 1

        await db.commit()
        logger.info("fixed_diary_event_timestamps", count=count)
        return count


async def auto_confirm_old_events() -> int:
    """自动确认超过24小时的事件，返回确认的数量"""
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id FROM timeline_events WHERE is_confirmed = 0 AND created_at < ?",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        event_ids = [row["id"] for row in rows]
        await db.execute(
            "UPDATE timeline_events SET is_confirmed = 1, confirmed_at = ? WHERE is_confirmed = 0 AND created_at < ?",
            (now, cutoff),
        )
        await db.commit()

    logger.info("auto_confirmed_events", count=len(event_ids))
    return len(event_ids)


async def confirm_timeline_event(event_id: str) -> TimelineEvent:
    """用户手动确认一个时间线事件"""
    event = await get_timeline_event(event_id)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="时间线事件不存在")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as db:
        await db.execute(
            "UPDATE timeline_events SET is_confirmed = 1, confirmed_at = ? WHERE id = ?",
            (now, event_id),
        )
        await db.commit()

    event.is_confirmed = True
    event.confirmed_at = now
    return event


async def update_timeline_event(event_id: str, updates: dict) -> TimelineEvent:
    """用户手动编辑一个时间线事件（仅允许编辑未锁定的事件）"""
    event = await get_timeline_event(event_id)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="时间线事件不存在")

    # Check explicit lock first
    if event.is_locked:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail={"msg": "该时间线条目已锁定，不可修改", "is_locked": True, "locked_at": event.locked_at})

    # Check auto-lock conditions: confirmed or older than 24h
    should_lock = False
    if event.is_confirmed:
        should_lock = True
    else:
        cutoff = datetime.now() - timedelta(hours=24)
        try:
            created = datetime.strptime(event.created_at, "%Y-%m-%d %H:%M:%S")
            if created < cutoff:
                should_lock = True
        except (ValueError, TypeError):
            pass

    if should_lock:
        # Auto-lock the event
        async with get_connection() as db:
            await db.execute(
                "UPDATE timeline_events SET is_locked = 1, locked_at = datetime('now','localtime') WHERE id = ?",
                (event_id,),
            )
            await db.commit()
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail={"msg": "该时间线条目已锁定，不可修改", "is_locked": True, "locked_at": "just now"})

    # Only allow updating certain fields
    allowed_fields = {"summary", "content", "event_type", "timestamp", "importance_score", "is_milestone", "sentiment"}
    update_fields = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}

    if not update_fields:
        return event

    # Build SQL dynamically
    set_clauses = []
    values = []
    for field, value in update_fields.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)

    values.append(event_id)

    async with get_connection() as db:
        await db.execute(
            f"UPDATE timeline_events SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )
        await db.commit()

    # Return updated event
    updated = await get_timeline_event(event_id)

    # 同步向量库（summary 变化需重新计算 embedding；其他字段变化只需更新元数据）
    if "summary" in update_fields or "content" in update_fields:
        try:
            from app.services.vector_store import vector_store
            from app.utils.embedding import embed_texts
            vector = (await embed_texts([updated.summary]))[0]
            await vector_store.update_timeline_event(
                event_id=updated.id,
                timestamp=updated.timestamp,
                event_type=updated.event_type,
                summary=updated.summary,
                content=updated.content,
                source_type=updated.source_type,
                source_id=updated.source_id or "",
                vector=vector,
            )
        except Exception as e:
            logger.warning("timeline_vector_update_failed", event_id=event_id, error=str(e))

    return updated


async def lock_timeline_event(event_id: str) -> dict:
    """手动锁定一条时间线事件"""
    event = await get_timeline_event(event_id)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="时间线事件不存在")

    if event.is_locked:
        return {"ok": True, "is_locked": True, "locked_at": event.locked_at}

    async with get_connection() as db:
        await db.execute(
            "UPDATE timeline_events SET is_locked = 1, locked_at = datetime('now','localtime') WHERE id = ?",
            (event_id,),
        )
        await db.commit()

    return {"ok": True, "is_locked": True, "locked_at": "just now"}


async def auto_lock_expired_events() -> int:
    """批量锁定超过 24 小时的未锁定事件。返回锁定的条目数。"""
    cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as db:
        cursor = await db.execute(
            "UPDATE timeline_events SET is_locked = 1, locked_at = datetime('now','localtime') "
            "WHERE is_locked = 0 AND is_confirmed = 0 AND created_at < ?",
            (cutoff,),
        )
        await db.commit()
        return cursor.rowcount


async def check_event_readonly(event_id: str) -> None:
    """检查事件是否为只读（已确认或超过24小时），如果是则抛出403异常"""
    event = await get_timeline_event(event_id)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="时间线事件不存在")

    if event.is_confirmed:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="该时间线条目已锁定，不可修改")

    cutoff = datetime.now() - timedelta(hours=24)
    try:
        created = datetime.strptime(event.created_at, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return

    if created < cutoff:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="该时间线条目已锁定，不可修改")


async def delete_timeline_event(event_id: str) -> dict:
    """删除一个时间线事件，同时清理 pages.timeline 中对该事件的引用"""
    event = await get_timeline_event(event_id)
    if event is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="时间线事件不存在")

    async with get_connection() as db:
        # 1. Delete the event itself
        await db.execute("DELETE FROM timeline_events WHERE id = ?", (event_id,))

        # 2. Clean up pages.timeline JSON - remove entries referencing this event
        # Get all pages that might reference this event via related_page_slugs
        if event.related_page_slugs:
            raw_slugs = event.related_page_slugs
            if raw_slugs.startswith("["):
                try:
                    import json
                    page_slugs = json.loads(raw_slugs)
                except Exception:
                    page_slugs = [s.strip() for s in raw_slugs.split(",") if s.strip()]
            else:
                page_slugs = [s.strip() for s in raw_slugs.split(",") if s.strip()]

            for slug in page_slugs:
                cursor = await db.execute("SELECT slug, timeline FROM pages WHERE slug = ?", (slug,))
                page_row = await cursor.fetchone()
                if page_row and page_row["timeline"]:
                    try:
                        import json
                        tl_entries = json.loads(page_row["timeline"])
                        # Remove entries that reference this event_id
                        original_len = len(tl_entries)
                        tl_entries = [e for e in tl_entries if e.get("source_id") != event_id and e.get("id") != event_id]
                        if len(tl_entries) < original_len:
                            await db.execute(
                                "UPDATE pages SET timeline = ? WHERE slug = ?",
                                (json.dumps(tl_entries, ensure_ascii=False), slug),
                            )
                    except (json.JSONDecodeError, TypeError):
                        pass

        await db.commit()

    # 同步删除向量库中的对应记录
    try:
        from app.services.vector_store import vector_store
        await vector_store.delete_timeline_event(event_id)
    except Exception as e:
        logger.warning("timeline_vector_delete_failed", event_id=event_id, error=str(e))

    logger.info("deleted_timeline_event", event_id=event_id)
    return {"ok": True, "deleted_id": event_id}


async def link_timeline_to_pages(page_slug: str, page_title: str) -> int:
    """将时间线事件关联到页面。在编译完成后调用，更新 related_page_slugs。
    返回更新的条目数。"""
    async with get_connection() as db:
        # Find timeline events where content or summary mentions the page title
        cursor = await db.execute(
            "SELECT id, related_page_slugs FROM timeline_events "
            "WHERE (summary LIKE ? OR content LIKE ?) "
            "AND (related_page_slugs IS NULL OR related_page_slugs NOT LIKE ?)",
            (f"%{page_title}%", f"%{page_title}%", f"%{page_slug}%"),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        count = 0
        for row in rows:
            current_slugs = row["related_page_slugs"] or ""
            slug_list = [s.strip() for s in current_slugs.split(",") if s.strip()]
            if page_slug not in slug_list:
                slug_list.append(page_slug)
            new_slugs = ",".join(slug_list)
            await db.execute(
                "UPDATE timeline_events SET related_page_slugs = ? WHERE id = ?",
                (new_slugs, row["id"]),
            )
            count += 1

        await db.commit()
        logger.info("linked_timeline_to_pages", page_slug=page_slug, count=count)
        return count


async def _build_event_context(
    diary_summary: str,
    diary_tags: str,
    diary_date: str,
) -> str:
    """为事件提取构建叙事背景 context。

    context 由 4 部分组成：
    1. 作者画像（pages 表 type='system' 的最新月度画像，无则标注暂无）
    2. 关键人物关系（links 表查询，提取 link_type 和 confidence）
    3. 近期时间线事件（最近7天，格式化为文本，同时作为画像保底）
    4. 本篇日记整体基调（diary_summary + tags）
    """
    sections: list[str] = []

    # 1. 获取作者画像（优先月度画像）
    try:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT compiled_truth FROM pages WHERE type='system' "
                "AND slug LIKE 'monthly_profile_%' AND compiled_truth != '' "
                "ORDER BY slug DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            author_profile = dict(row)["compiled_truth"] if row else ""
    except Exception:
        author_profile = ""

    if author_profile:
        sections.append(f"【作者画像】\n{author_profile[:500]}")
    else:
        sections.append("【作者画像】\n（暂无 compiled 画像，参考下方近期事件）")

    # 2. 获取人物关系（links 表）
    try:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT sp.title as source, tp.title as target, l.link_type, l.confidence "
                "FROM links l "
                "JOIN pages sp ON sp.id = l.source_page_id "
                "JOIN pages tp ON tp.id = l.target_page_id "
                "WHERE sp.type != 'system' AND tp.type != 'system' "
                "ORDER BY l.rowid DESC LIMIT 30"
            )
            rows = await cursor.fetchall()
            relationships = []
            for r in rows:
                rel_text = f"{r['source']} → {r['target']}（{r['link_type'] or '关联'}"
                if r["confidence"]:
                    rel_text += f"，{r['confidence']}"
                rel_text += "）"
                relationships.append(rel_text)
    except Exception:
        relationships = []

    if relationships:
        sections.append(f"【关键人物关系】\n{chr(10).join(relationships)}")
    else:
        sections.append("【关键人物关系】\n（暂无已识别关系）")

    # 3. 获取近期时间线事件（最近7天）
    try:
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT timestamp, event_type, summary, sentiment "
                "FROM timeline_events WHERE timestamp >= ? "
                "ORDER BY timestamp DESC LIMIT 20",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            recent_events = []
            for r in rows:
                event_text = f"[{r['timestamp']}] [{r['event_type']}] {r['summary']}"
                if r["sentiment"] is not None:
                    event_text += f" (情绪: {r['sentiment']})"
                recent_events.append(event_text)
    except Exception:
        recent_events = []

    if recent_events:
        sections.append(f"【近期时间线事件（最近7天）】\n{chr(10).join(recent_events)}")

    # 4. 本篇日记整体基调
    sections.append(
        f"【本篇日记整体基调】\n摘要：{diary_summary}\n标签：{diary_tags}\n日期：{diary_date}"
    )

    return "\n\n".join(sections)
