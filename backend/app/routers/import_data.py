from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import get_connection

from app.services.importer.wechat import (
    import_wechat_stats,
    import_wechat_tier2,
    import_wechat_tier3,
    extract_wechat_signals,
    get_import_batches,
    delete_import_batch,
    get_privacy_info,
    update_privacy,
    analyze_tier2_data,
    analyze_tier3_data,
    cleanup_expired_tier3,
)
from app.services.importer.alipay import import_alipay_csv
from app.services.importer.wechat_pay import import_wechat_pay_csv
from app.services.importer.social_media import import_social_media
from app.services.importer.media import import_media_records
from app.services.importer.consumption_processor import (
    parse_consumption_csv,
    infer_habits_from_consumption,
    confirm_and_write_habits,
)

router = APIRouter(prefix="/api/import", tags=["import"])

MEDIA_TYPE_MAP = {
    "书籍": "book",
    "书": "book",
    "电影": "movie",
    "电视剧": "tv_series",
    "剧": "tv_series",
    "动漫": "tv_series",
    "音乐": "music",
    "播客": "podcast",
}


class WechatImportRequest(BaseModel):
    contact_name: str
    messages: list[dict]
    privacy_tier: str = "tier1"


class WechatTier2Request(BaseModel):
    contact_name: str
    messages: list[dict]


class WechatTier3Request(BaseModel):
    contact_name: str
    messages: list[dict]


class PrivacyUpdateRequest(BaseModel):
    privacy_tier: str
    tier2_authorized: bool = False
    tier3_authorized: bool = False


class AlipayImportRequest(BaseModel):
    csv_content: str


class WechatPayImportRequest(BaseModel):
    csv_content: str


class SocialMediaImportRequest(BaseModel):
    platform: str
    data: list[dict]


class SingleMediaImportRequest(BaseModel):
    title: str
    media_type: str = "书籍"
    consumed_date: str | None = None
    rating: float | None = None
    notes: str | None = None


class MediaImportRequest(BaseModel):
    data: list[dict]


class ConsumptionConfirmRequest(BaseModel):
    items: list[dict]
    habits: list[dict]


class DiaryImportRequest(BaseModel):
    entries: list[dict]


@router.post("/wechat")
async def api_import_wechat(body: WechatImportRequest):
    if not body.messages:
        raise HTTPException(status_code=400, detail="消息列表不能为空")
    result = await import_wechat_stats(
        contact_name=body.contact_name,
        messages=body.messages,
        privacy_tier=body.privacy_tier,
    )
    return result


@router.post("/wechat/tier2")
async def api_import_wechat_tier2(body: WechatTier2Request):
    if not body.messages:
        raise HTTPException(status_code=400, detail="消息列表不能为空")
    result = await import_wechat_tier2(
        contact_name=body.contact_name,
        messages=body.messages,
    )
    return result


@router.post("/wechat/tier3")
async def api_import_wechat_tier3(body: WechatTier3Request):
    if not body.messages:
        raise HTTPException(status_code=400, detail="消息列表不能为空")
    result = await import_wechat_tier3(
        contact_name=body.contact_name,
        messages=body.messages,
    )
    return result


@router.get("/batches")
async def api_get_batches():
    batches = await get_import_batches()
    return batches


@router.delete("/{batch_id}")
async def api_delete_batch(batch_id: str):
    deleted = await delete_import_batch(batch_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {"status": "deleted"}


@router.get("/privacy/{contact_name}")
async def api_get_privacy(contact_name: str):
    info = await get_privacy_info(contact_name)
    if info is None:
        return {
            "contact_name": contact_name,
            "privacy_tier": "tier1",
            "tier2_authorized": False,
            "tier3_authorized": False,
            "tier3_expires_at": None,
        }
    return info


@router.put("/privacy/{contact_name}")
async def api_update_privacy(contact_name: str, body: PrivacyUpdateRequest):
    result = await update_privacy(
        contact_name=contact_name,
        privacy_tier=body.privacy_tier,
        tier2_authorized=body.tier2_authorized,
        tier3_authorized=body.tier3_authorized,
    )
    return result


@router.get("/signals/{contact_name}")
async def api_extract_signals(contact_name: str):
    signals = await extract_wechat_signals(contact_name)
    return {"contact_name": contact_name, "signals": signals}


@router.post("/analyze/tier2/{contact_name}")
async def api_analyze_tier2(contact_name: str):
    info = await get_privacy_info(contact_name)
    if not info or not info.get("tier2_authorized"):
        raise HTTPException(status_code=403, detail="未获得 Tier 2 授权")
    signals = await analyze_tier2_data(contact_name)
    return {"contact_name": contact_name, "signals": signals}


@router.post("/analyze/tier3/{contact_name}")
async def api_analyze_tier3(contact_name: str):
    info = await get_privacy_info(contact_name)
    if not info or not info.get("tier3_authorized"):
        raise HTTPException(status_code=403, detail="未获得 Tier 3 授权")
    signals = await analyze_tier3_data(contact_name)
    return {"contact_name": contact_name, "signals": signals, "note": "Tier 3 原文已自动清除"}


@router.post("/cleanup/expired")
async def api_cleanup_expired():
    deleted = await cleanup_expired_tier3()
    return {"deleted_count": deleted}


@router.post("/alipay")
async def api_import_alipay(body: AlipayImportRequest):
    if not body.csv_content.strip():
        raise HTTPException(status_code=400, detail="CSV内容不能为空")
    result = await import_alipay_csv(csv_content=body.csv_content)
    return result


@router.post("/wechat-pay")
async def api_import_wechat_pay(body: WechatPayImportRequest):
    if not body.csv_content.strip():
        raise HTTPException(status_code=400, detail="CSV内容不能为空")
    result = await import_wechat_pay_csv(csv_content=body.csv_content)
    return result


@router.post("/social")
async def api_import_social(body: SocialMediaImportRequest):
    if not body.data:
        raise HTTPException(status_code=400, detail="数据列表不能为空")
    result = await import_social_media(data=body.data, platform=body.platform)
    return result


@router.post("/media")
async def api_import_media(body: SingleMediaImportRequest):
    """录入单条书影音记录"""
    import uuid
    from datetime import datetime
    record_id = uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as db:
        await db.execute(
            "INSERT INTO media_records (id, title, media_type, consumed_date, rating, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record_id, body.title, body.media_type, body.consumed_date, body.rating, body.notes, now),
        )
        await db.commit()

    asyncio.create_task(_process_media_async(record_id, body.title, body.media_type, body.rating, body.notes, body.consumed_date))

    return {"kb_id": record_id, "message": "录入成功，知识库后台构建中", "knowledge_status": "pending"}


async def _process_media_async(record_id: str, title: str, media_type: str, rating: float | None, notes: str | None, consumed_date: str | None):
    import structlog

    logger = structlog.get_logger()

    try:
        data = [{"title": title, "type": media_type, "rating": rating or 0, "notes": notes or "", "consumed_date": consumed_date or ""}]
        await import_media_records(data=data, import_batch_id=record_id)

        from app.services.knowledge import find_knowledge_by_title_fuzzy, create_knowledge_item

        existing = await find_knowledge_by_title_fuzzy(title)
        if existing:
            logger.info("知识条目已存在，跳过创建", title=title)
            return

        kb_type = MEDIA_TYPE_MAP.get(media_type, "book")

        from app.services.search import search_service
        from app.prompts.knowledge_extraction import KNOWLEDGE_EXTRACTION_PROMPT
        from app.utils.llm import chat_completion

        search_results = await asyncio.wait_for(
            search_service.search(title),
            timeout=5.0,
        )
        if not search_results:
            logger.warning("联网搜索无结果", title=title)
            return

        all_content = json.dumps(search_results, ensure_ascii=False)
        response = await asyncio.wait_for(
            chat_completion(
                messages=[{
                    "role": "user",
                    "content": KNOWLEDGE_EXTRACTION_PROMPT.format(
                        title=title,
                        media_type=kb_type,
                        search_results=all_content,
                    ),
                }],
                temperature=0.2,
            ),
            timeout=6.0,
        )

        extracted = json.loads(response)
        if isinstance(extracted, dict) and extracted.get("title"):
            extracted["type"] = kb_type
            extracted["user_status"] = "consumed" if consumed_date else "mentioned"
            extracted["user_consumed_date"] = consumed_date
            extracted["user_rating"] = rating
            extracted["user_notes"] = notes
            await create_knowledge_item(extracted)

            from app.services.gbrain_page import upsert_page, _generate_slug
            from app.services.signals import extract_and_log_signals

            summary = extracted.get("summary", "") or ""
            slug = _generate_slug(title)
            await upsert_page({
                "slug": slug,
                "type": "media",
                "title": title,
                "compiled_truth": summary,
                "frontmatter": {
                    "source": "media_import",
                    "media_type": kb_type,
                    "consumed_date": consumed_date,
                    "rating": rating,
                    "notes": notes,
                },
            })

            if notes:
                await extract_and_log_signals(notes, source_type="media", source_id=record_id)

            logger.info("知识条目创建成功", title=title, kb_type=kb_type)
        else:
            logger.warning("LLM 提取结果缺少 title", title=title, response=response[:100])

    except asyncio.TimeoutError:
        logger.warning("知识创建超时", title=title)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("知识创建 JSON 解析失败", title=title, error=str(e))
    except Exception as e:
        logger.exception("知识创建失败", title=title, error=str(e))


@router.get("/media")
async def list_media_records(
    media_type: str = Query(default=None),
    q: str = Query(default=None),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
):
    """获取书影音记录列表"""
    async with get_connection() as db:
        sql = "SELECT id, title, media_type, consumed_date, rating, notes, created_at FROM media_records WHERE 1=1"
        params: list = []
        if media_type:
            sql += " AND media_type = ?"
            params.append(media_type)
        if q:
            sql += " AND title LIKE ?"
            params.append(f"%{q}%")
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


class ConsumptionUploadRequest(BaseModel):
    csv_content: str
    source: str = "alipay"


@router.post("/consumption")
async def api_import_consumption(body: ConsumptionUploadRequest):
    """Upload CSV, parse and return structured items + inferred habits."""
    if not body.csv_content.strip():
        raise HTTPException(status_code=400, detail="CSV内容不能为空")
    if body.source not in ("alipay", "wechat_pay"):
        raise HTTPException(status_code=400, detail="source 必须是 alipay 或 wechat_pay")

    items = parse_consumption_csv(body.csv_content, body.source)
    if not items:
        return {"items": [], "inferred_habits": []}

    inferred_habits = await infer_habits_from_consumption(items)

    return {"items": items, "inferred_habits": inferred_habits}


@router.post("/consumption/confirm")
async def api_confirm_consumption(body: ConsumptionConfirmRequest):
    """Confirm selected items and habits to write."""
    from app.services.importer.consumption_base import (
        extract_consumption_signals,
        create_consumption_timeline_event,
        aggregate_consumption_stats,
    )
    import uuid

    written_count = 0
    habit_count = 0

    if body.items:
        import_batch_id = uuid.uuid4().hex
        records = []
        for item in body.items:
            records.append({
                "timestamp": item.get("date", ""),
                "merchant": item.get("merchant", ""),
                "description": item.get("description", ""),
                "amount": item.get("amount", 0),
                "type": "expense",
                "source": "consumption_import",
                "batch_id": import_batch_id,
            })

        signals = extract_consumption_signals(records)
        for signal in signals:
            await create_consumption_timeline_event(signal, import_batch_id)
        await aggregate_consumption_stats(signals, import_batch_id)
        written_count = len(body.items)

    if body.habits:
        habit_count = await confirm_and_write_habits(body.habits)

    return {"written_count": written_count, "habit_count": habit_count}


@router.post("/diary")
async def api_import_diary(body: DiaryImportRequest):
    """Batch import diary entries with sequential processing to avoid LLM rate limiting."""
    if not body.entries:
        raise HTTPException(status_code=400, detail="日记条目不能为空")

    import structlog
    from app.services.diary import create_diary, process_diary_async

    logger = structlog.get_logger()

    # Sort entries by date before processing (oldest first)
    sorted_entries = sorted(body.entries, key=lambda e: e.get("date", ""))

    imported_ids: list[str] = []
    skipped = 0
    for entry in sorted_entries:
        date = entry.get("date", "")
        content = entry.get("content", "")
        if not date or not content:
            skipped += 1
            continue
        diary = await create_diary(date=date, content=content)
        imported_ids.append(diary.id)

    # Sequential processing with 2-second intervals and semaphore concurrency control
    semaphore = asyncio.Semaphore(2)
    processed = 0
    failed = 0

    async def _process_with_semaphore(did: str) -> bool:
        async with semaphore:
            return await process_diary_async(did)

    for i, did in enumerate(imported_ids):
        if i > 0:
            await asyncio.sleep(2)
        try:
            success = await _process_with_semaphore(did)
            if success:
                processed += 1
            else:
                failed += 1
        except Exception:
            logger.exception("日记处理失败", diary_id=did)
            failed += 1

    return {
        "imported_count": len(imported_ids),
        "processed_count": processed,
        "failed_count": failed,
        "skipped_count": skipped,
        "message": f"成功导入 {len(imported_ids)} 条日记，处理完成 {processed} 条，失败 {failed} 条",
    }


@router.get("/diary/pending")
async def api_get_pending_diaries():
    """获取未处理完成的日记列表（pending/failed），用于中断恢复检查"""
    from app.services.diary import get_pending_diaries
    pending = await get_pending_diaries()
    return {
        "count": len(pending),
        "entries": pending,
    }


@router.post("/diary/retry")
async def api_retry_failed_diaries():
    """重新处理所有失败的日记（pending/failed），用于中断恢复"""
    from app.services.diary import retry_failed_diaries
    result = await retry_failed_diaries()
    return result
