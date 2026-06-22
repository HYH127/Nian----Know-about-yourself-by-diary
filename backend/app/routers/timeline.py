from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.database import get_connection
from app.models.timeline import TimelineEvent
from app.services.timeline import (
    get_timeline_event,
    list_timeline_events,
    confirm_timeline_event,
    update_timeline_event,
    lock_timeline_event,
    auto_lock_expired_events,
    fix_diary_event_timestamps,
)

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


class TimelineEventUpdateRequest(BaseModel):
    summary: str | None = None
    content: str | None = None
    event_type: str | None = None
    timestamp: str | None = None
    importance_score: float | None = None
    is_milestone: bool | None = None
    sentiment: float | None = None


@router.get("", response_model=list[TimelineEvent])
async def api_list_timeline_events(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    event_type: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    contact: Optional[str] = Query(default=None),
    min_importance: Optional[float] = Query(default=None, ge=0.0, le=1.0),
):
    return await list_timeline_events(
        limit=limit,
        offset=offset,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        contact=contact,
        min_importance=min_importance,
    )


@router.get("/sentiment-stats")
async def api_sentiment_stats(
    period: str = Query(default="week", pattern="^(week|month|all)$"),
):
    """获取情绪统计，按日期聚合平均sentiment。period: week(前7天)/month(前30天)/all(全部)"""
    now = datetime.now()
    if period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        start = None

    async with get_connection() as db:
        if start:
            cursor = await db.execute(
                "SELECT SUBSTR(timestamp, 1, 10) as date, AVG(sentiment) as avg_sentiment, COUNT(*) as count "
                "FROM timeline_events WHERE sentiment IS NOT NULL AND timestamp >= ? "
                "GROUP BY SUBSTR(timestamp, 1, 10) ORDER BY date",
                (start.strftime("%Y-%m-%d"),),
            )
        else:
            cursor = await db.execute(
                "SELECT SUBSTR(timestamp, 1, 10) as date, AVG(sentiment) as avg_sentiment, COUNT(*) as count "
                "FROM timeline_events WHERE sentiment IS NOT NULL "
                "GROUP BY SUBSTR(timestamp, 1, 10) ORDER BY date",
            )
        rows = await cursor.fetchall()

    return [
        {"date": row["date"], "avg_sentiment": round(row["avg_sentiment"], 3), "count": row["count"]}
        for row in rows
    ]


@router.get("/overview-stats")
async def api_overview_stats():
    """获取统计概览的全部数据（不受分页影响）"""
    async with get_connection() as db:
        # Total count
        cursor = await db.execute("SELECT COUNT(*) as total FROM timeline_events")
        row = await cursor.fetchone()
        total = row["total"]

        # Type counts
        cursor = await db.execute(
            "SELECT event_type, COUNT(*) as count FROM timeline_events GROUP BY event_type ORDER BY count DESC"
        )
        type_rows = await cursor.fetchall()
        type_counts = {row["event_type"]: row["count"] for row in type_rows}

        # Sentiment counts
        cursor = await db.execute(
            "SELECT "
            "SUM(CASE WHEN sentiment > 0.3 THEN 1 ELSE 0 END) as pos_count, "
            "SUM(CASE WHEN sentiment < -0.3 THEN 1 ELSE 0 END) as neg_count, "
            "SUM(CASE WHEN sentiment IS NOT NULL AND sentiment >= -0.3 AND sentiment <= 0.3 THEN 1 ELSE 0 END) as neutral_count, "
            "SUM(CASE WHEN sentiment IS NULL THEN 1 ELSE 0 END) as no_sentiment "
            "FROM timeline_events"
        )
        row = await cursor.fetchone()
        sentiment = {
            "pos_count": row["pos_count"] or 0,
            "neg_count": row["neg_count"] or 0,
            "neutral_count": row["neutral_count"] or 0,
            "no_sentiment": row["no_sentiment"] or 0,
        }

    return {"total": total, "type_counts": type_counts, "sentiment": sentiment}


@router.get("/{event_id}", response_model=TimelineEvent)
async def api_get_timeline_event(event_id: str):
    event = await get_timeline_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="时间线事件不存在")
    return event


@router.put("/events/{event_id}/confirm", response_model=TimelineEvent)
async def api_confirm_timeline_event(event_id: str):
    return await confirm_timeline_event(event_id)


@router.put("/events/{event_id}", response_model=TimelineEvent)
async def api_update_timeline_event(event_id: str, body: TimelineEventUpdateRequest):
    updates = body.model_dump(exclude_none=True)
    return await update_timeline_event(event_id, updates)


@router.post("/events/{event_id}/lock")
async def api_lock_timeline_event(event_id: str):
    """手动锁定一条时间线事件，锁定后不可修改"""
    return await lock_timeline_event(event_id)


@router.post("/auto-lock")
async def api_auto_lock_expired():
    """批量锁定超过 24 小时的未锁定事件"""
    count = await auto_lock_expired_events()
    return {"locked_count": count}


@router.post("/fix-timestamps")
async def api_fix_timestamps():
    """修正所有 diary 来源事件的时间戳，用对应日记的 date 替换错误的 timestamp"""
    count = await fix_diary_event_timestamps()
    return {"fixed_count": count}
