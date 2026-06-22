from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

import structlog

from app.database import get_connection
from app.services.timeline import update_timeline_event, delete_timeline_event

logger = structlog.get_logger()

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class DiaryStatus(BaseModel):
    total: int
    processed: int
    pending: int


class TimelineStatus(BaseModel):
    total: int
    confirmed: int
    unconfirmed: int


class PagesStatus(BaseModel):
    total: int
    compiled: int
    uncompiled: int


class PortraitsStatus(BaseModel):
    detailed: int
    deep: int


class MonitorEventUpdateRequest(BaseModel):
    summary: str | None = None
    event_type: str | None = None
    timestamp: str | None = None
    importance_score: float | None = None


class MonitorStatus(BaseModel):
    diaries: DiaryStatus
    timeline_events: TimelineStatus
    pages: PagesStatus
    portraits: PortraitsStatus


class UnconfirmedEvent(BaseModel):
    id: str
    timestamp: str
    summary: str
    event_type: str
    source_type: str
    page_slugs: list[str]
    importance_score: float = 0.5


class MonitorPending(BaseModel):
    unconfirmed_events: list[UnconfirmedEvent]


@router.get("/status", response_model=MonitorStatus)
async def get_monitor_status():
    async with get_connection() as db:
        # Diaries
        row = await db.execute("SELECT COUNT(*) as cnt FROM diaries")
        diary_total = (await row.fetchone())["cnt"]
        row = await db.execute("SELECT COUNT(*) as cnt FROM diaries WHERE extracted_summary IS NOT NULL AND extracted_summary != ''")
        diary_processed = (await row.fetchone())["cnt"]

        # Timeline events
        row = await db.execute("SELECT COUNT(*) as cnt FROM timeline_events")
        tl_total = (await row.fetchone())["cnt"]
        row = await db.execute("SELECT COUNT(*) as cnt FROM timeline_events WHERE is_confirmed = 1")
        tl_confirmed = (await row.fetchone())["cnt"]

        # Pages
        row = await db.execute("SELECT COUNT(*) as cnt FROM pages")
        pages_total = (await row.fetchone())["cnt"]
        row = await db.execute("SELECT COUNT(*) as cnt FROM pages WHERE compiled_truth IS NOT NULL AND compiled_truth != ''")
        pages_compiled = (await row.fetchone())["cnt"]

        # Portraits
        row = await db.execute("SELECT COUNT(*) as cnt FROM portrait_records WHERE portrait_type = 'detailed' AND is_current = 1")
        portrait_detailed = (await row.fetchone())["cnt"]
        row = await db.execute("SELECT COUNT(*) as cnt FROM portrait_records WHERE portrait_type = 'deep' AND is_current = 1")
        portrait_deep = (await row.fetchone())["cnt"]

    return MonitorStatus(
        diaries=DiaryStatus(
            total=diary_total,
            processed=diary_processed,
            pending=diary_total - diary_processed,
        ),
        timeline_events=TimelineStatus(
            total=tl_total,
            confirmed=tl_confirmed,
            unconfirmed=tl_total - tl_confirmed,
        ),
        pages=PagesStatus(
            total=pages_total,
            compiled=pages_compiled,
            uncompiled=pages_total - pages_compiled,
        ),
        portraits=PortraitsStatus(
            detailed=portrait_detailed,
            deep=portrait_deep,
        ),
    )


@router.get("/pending", response_model=MonitorPending)
async def get_monitor_pending():
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, timestamp, summary, event_type, source_type, related_page_slugs, importance_score
            FROM timeline_events
            WHERE is_confirmed = 0
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
        rows = await cursor.fetchall()

    events = []
    for row in rows:
        page_slugs_raw = row["related_page_slugs"] or ""
        page_slugs = []
        if page_slugs_raw:
            try:
                import json
                parsed = json.loads(page_slugs_raw)
                if isinstance(parsed, list):
                    page_slugs = [str(s) for s in parsed]
            except Exception:
                page_slugs = [s.strip() for s in page_slugs_raw.split(",") if s.strip()]

        events.append(UnconfirmedEvent(
            id=row["id"],
            timestamp=row["timestamp"],
            summary=row["summary"],
            event_type=row["event_type"],
            source_type=row["source_type"],
            page_slugs=page_slugs,
            importance_score=row["importance_score"],
        ))

    return MonitorPending(unconfirmed_events=events)


class FailedDiaryItem(BaseModel):
    id: str
    date: str
    content_preview: str
    created_at: str


class FailedDiaryStatus(BaseModel):
    failed_count: int
    failed_diaries: list[FailedDiaryItem]


class RetryFailedResult(BaseModel):
    retried_count: int
    success_count: int
    still_failed_count: int
    failed_ids: list[str]


@router.get("/failed-diaries", response_model=FailedDiaryStatus)
async def get_failed_diaries():
    """获取处理失败的日记：extracted_summary 为空且 created_at 超过5分钟的日记"""
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id, date, content, created_at
            FROM diaries
            WHERE (extracted_summary IS NULL OR extracted_summary = '')
              AND datetime(created_at) <= datetime('now', 'localtime', '-5 minutes')
            ORDER BY created_at ASC
            """
        )
        rows = await cursor.fetchall()

    failed_diaries = []
    for row in rows:
        content_preview = (row["content"] or "")[:100]
        failed_diaries.append(FailedDiaryItem(
            id=row["id"],
            date=row["date"],
            content_preview=content_preview,
            created_at=row["created_at"],
        ))

    return FailedDiaryStatus(
        failed_count=len(failed_diaries),
        failed_diaries=failed_diaries,
    )


@router.post("/retry-failed", response_model=RetryFailedResult)
async def retry_failed_diaries():
    """批量重试处理失败的日记"""
    from app.services.diary import process_diary_async

    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT id
            FROM diaries
            WHERE (extracted_summary IS NULL OR extracted_summary = '')
              AND datetime(created_at) <= datetime('now', 'localtime', '-5 minutes')
            ORDER BY created_at ASC
            """
        )
        rows = await cursor.fetchall()

    if not rows:
        return RetryFailedResult(retried_count=0, success_count=0, still_failed_count=0, failed_ids=[])

    semaphore = asyncio.Semaphore(2)
    success_count = 0
    still_failed_ids: list[str] = []

    async def _process_with_semaphore(did: str) -> tuple[str, bool]:
        async with semaphore:
            result = await process_diary_async(did)
            return did, result

    for i, row in enumerate(rows):
        did = row["id"]
        if i > 0:
            await asyncio.sleep(2)
        try:
            _, success = await _process_with_semaphore(did)
            if success:
                success_count += 1
            else:
                still_failed_ids.append(did)
        except Exception:
            logger.exception("批量重试日记处理异常", diary_id=did)
            still_failed_ids.append(did)

    return RetryFailedResult(
        retried_count=len(rows),
        success_count=success_count,
        still_failed_count=len(still_failed_ids),
        failed_ids=still_failed_ids,
    )


@router.delete("/events/{event_id}")
async def api_delete_monitor_event(event_id: str):
    """删除一个待确认的时间线事件，同时清理实体页面中的引用"""
    return await delete_timeline_event(event_id)


@router.put("/events/{event_id}")
async def api_update_monitor_event(event_id: str, body: MonitorEventUpdateRequest):
    """编辑一个待确认的时间线事件"""
    updates = body.model_dump(exclude_none=True)
    return await update_timeline_event(event_id, updates)
