from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.diary import DiaryCreate, DiaryUpdate, Diary, DiarySearchResult, DiaryDateItem
from app.services.diary import (
    create_diary,
    get_diary,
    list_diaries,
    search_diaries,
    list_diary_dates,
    delete_diary,
    update_diary,
    process_diary_async,
    check_diary_duplicates,
)

router = APIRouter(prefix="/api/diary", tags=["diary"])


class DuplicateCheckRequest(BaseModel):
    entries: list[dict]


@router.get("/weather")
async def api_get_weather(
    latitude: float = Query(..., description="纬度"),
    longitude: float = Query(..., description="经度"),
):
    """根据经纬度获取位置和天气信息"""
    from app.services.weather_service import get_location_weather
    result = await get_location_weather(latitude, longitude)
    return result


@router.post("/check-duplicate")
async def api_check_duplicate(body: DuplicateCheckRequest):
    """Check which diary entries are duplicates of existing ones."""
    results = await check_diary_duplicates(body.entries)
    return {"duplicates": results}


@router.post("", response_model=Diary)
async def api_create_diary(body: DiaryCreate):
    diary = await create_diary(
        date=body.date,
        content=body.content,
        location=body.location,
        weather=body.weather,
        temperature=body.temperature,
        humidity=body.humidity,
    )
    asyncio.create_task(process_diary_async(diary.id))
    return diary


@router.get("", response_model=list[Diary])
async def api_list_diaries(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await list_diaries(limit=limit, offset=offset)


@router.get("/search", response_model=list[DiarySearchResult])
async def api_search_diaries(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
):
    return await search_diaries(query=q, limit=limit)


@router.get("/dates/list", response_model=list[DiaryDateItem])
async def api_list_diary_dates():
    return await list_diary_dates()


@router.post("/reprocess-all")
async def api_reprocess_all_diaries():
    """重新处理所有日记（用于修复之前LLM返回空导致缺失时间线/实体的问题）"""
    from app.database import get_connection
    async with get_connection() as db:
        cursor = await db.execute("SELECT id FROM diaries ORDER BY date")
        rows = await cursor.fetchall()

    async def _process_all():
        for i, row in enumerate(rows):
            if i > 0:
                await asyncio.sleep(2)
            try:
                await process_diary_async(row["id"])
            except Exception:
                pass

    asyncio.create_task(_process_all())
    return {"ok": True, "message": f"已触发重新处理 {len(rows)} 条日记"}


@router.get("/{diary_id}", response_model=Diary)
async def api_get_diary(diary_id: str):
    diary = await get_diary(diary_id)
    if diary is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    return diary


@router.put("/{diary_id}", response_model=Diary)
async def api_update_diary(diary_id: str, body: DiaryUpdate):
    diary = await get_diary(diary_id)
    if diary is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    updated = await update_diary(diary_id, content=body.content, date=body.date)
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    return updated


@router.delete("/{diary_id}")
async def api_delete_diary(diary_id: str):
    await delete_diary(diary_id)
    return {"ok": True}


@router.post("/{diary_id}/reprocess")
async def api_reprocess_diary(diary_id: str):
    """重新处理单条日记（摘要提取、信号提取等）"""
    diary = await get_diary(diary_id)
    if diary is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    asyncio.create_task(process_diary_async(diary_id))
    return {"ok": True, "message": "已触发重新处理"}
