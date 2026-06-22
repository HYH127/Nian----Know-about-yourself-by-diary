from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.models.quicknote import (
    QuickNoteCreate,
    QuickNoteUpdate,
    QuickNote,
    ExpenseRecordCreate,
    ExpenseRecordUpdate,
    ExpenseRecord,
    ExpenseStats,
)
from app.services.quicknote import (
    create_quick_note,
    get_quick_note,
    update_quick_note,
    delete_quick_note,
    list_quick_notes,
    process_quicknote_async,
    create_expense_record,
    get_expense_record,
    update_expense_record,
    delete_expense_record,
    list_expense_records,
    get_expense_stats,
)

router = APIRouter(prefix="/api/quicknote", tags=["quicknote"])


# ── Expense Record endpoints (MUST be before /{note_id} to avoid path collision) ──

@router.post("/expense", response_model=ExpenseRecord)
async def api_create_expense_record(body: ExpenseRecordCreate):
    return await create_expense_record(
        amount=body.amount,
        category=body.category,
        description=body.description,
        note=body.note,
        expense_date=body.expense_date,
    )


@router.get("/expense/stats", response_model=ExpenseStats)
async def api_get_expense_stats(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
):
    return await get_expense_stats(start_date=start_date, end_date=end_date)


@router.get("/expense", response_model=list[ExpenseRecord])
async def api_list_expense_records(
    expense_date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return await list_expense_records(
        expense_date=expense_date,
        category=category,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.put("/expense/{record_id}", response_model=ExpenseRecord)
async def api_update_expense_record(record_id: str, body: ExpenseRecordUpdate):
    record = await get_expense_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="消费记录不存在")
    updated = await update_expense_record(record_id, **body.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    return updated


@router.delete("/expense/{record_id}")
async def api_delete_expense_record(record_id: str):
    await delete_expense_record(record_id)
    return {"ok": True}


# ── Quick Note endpoints ──

@router.post("", response_model=QuickNote)
async def api_create_quick_note(body: QuickNoteCreate):
    note = await create_quick_note(content=body.content)
    asyncio.create_task(process_quicknote_async(note.id))
    return note


@router.get("", response_model=list[QuickNote])
async def api_list_quick_notes(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return await list_quick_notes(limit=limit, offset=offset)


@router.get("/{note_id}", response_model=QuickNote)
async def api_get_quick_note(note_id: str):
    note = await get_quick_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="随手记不存在")
    return note


@router.put("/{note_id}", response_model=QuickNote)
async def api_update_quick_note(note_id: str, body: QuickNoteUpdate):
    note = await get_quick_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="随手记不存在")
    updated = await update_quick_note(note_id, content=body.content)
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    # Re-process after update
    asyncio.create_task(process_quicknote_async(note_id))
    return updated


@router.delete("/{note_id}")
async def api_delete_quick_note(note_id: str):
    await delete_quick_note(note_id)
    return {"ok": True}


@router.post("/{note_id}/reprocess")
async def api_reprocess_quick_note(note_id: str):
    note = await get_quick_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="随手记不存在")
    asyncio.create_task(process_quicknote_async(note_id))
    return {"ok": True, "message": "已触发重新处理"}
