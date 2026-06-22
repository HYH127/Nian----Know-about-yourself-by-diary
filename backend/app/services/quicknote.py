from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime

import structlog

from app.database import get_connection
from app.models.quicknote import QuickNote, ExpenseRecord
from app.services.signal_extractor import extract_signals
from app.utils.llm import chat_completion

logger = structlog.get_logger()

# ── Completeness check prompt ──
_COMPLETENESS_PROMPT = """判断以下文本是否包含完整、有意义的信息（而非无意义的碎片如"嗯"、"测试"、单个词等）。
只回答 true 或 false。

文本：{text}"""


# ═══════════════════════════════════════════
# Quick Note CRUD
# ═══════════════════════════════════════════

async def create_quick_note(content: str) -> QuickNote:
    note_id = uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as db:
        await db.execute(
            "INSERT INTO quick_notes (id, content, edited_at, created_at, processing_status) VALUES (?, ?, ?, ?, ?)",
            (note_id, content, now, now, "pending"),
        )
        await db.commit()
    return QuickNote(id=note_id, content=content, edited_at=now, created_at=now)


async def get_quick_note(note_id: str) -> QuickNote | None:
    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM quick_notes WHERE id = ?", (note_id,))
        row = await cursor.fetchone()
    if row is None:
        return None
    return QuickNote(
        id=row["id"],
        content=row["content"],
        edited_at=row["edited_at"],
        created_at=row["created_at"],
        processing_status=row["processing_status"],
    )


async def update_quick_note(note_id: str, content: str) -> QuickNote | None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as db:
        await db.execute(
            "UPDATE quick_notes SET content = ?, edited_at = ? WHERE id = ?",
            (content, now, note_id),
        )
        await db.commit()
    return await get_quick_note(note_id)


async def delete_quick_note(note_id: str) -> None:
    async with get_connection() as db:
        await db.execute("DELETE FROM quick_notes WHERE id = ?", (note_id,))
        await db.commit()


async def list_quick_notes(limit: int = 50, offset: int = 0) -> list[QuickNote]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM quick_notes ORDER BY edited_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
    return [
        QuickNote(
            id=row["id"],
            content=row["content"],
            edited_at=row["edited_at"],
            created_at=row["created_at"],
            processing_status=row["processing_status"],
        )
        for row in rows
    ]


# ═══════════════════════════════════════════
# Quick Note Processing
# ═══════════════════════════════════════════

async def _check_completeness(text: str) -> bool:
    """用 LLM 判断内容是否完整有意义。"""
    try:
        raw = await chat_completion(
            messages=[{"role": "user", "content": _COMPLETENESS_PROMPT.format(text=text)}],
            temperature=0.0,
            max_tokens=10,
            purpose="随手记完整性判断",
        )
        return "true" in raw.lower()
    except Exception:
        # If LLM fails, be conservative and process anyway
        return True


async def _update_processing_status(note_id: str, status: str) -> None:
    try:
        async with get_connection() as db:
            await db.execute(
                "UPDATE quick_notes SET processing_status = ? WHERE id = ?",
                (status, note_id),
            )
            await db.commit()
    except Exception:
        logger.exception("更新随手记处理状态失败", note_id=note_id, status=status)


async def process_quicknote_async(note_id: str, max_retries: int = 2) -> bool:
    """随手记异步处理：完整性判断 → 信号提取

    注意：随手记不写入时间线和实体（仅日记可以写入时间线和实体）。
    """
    for attempt in range(max_retries + 1):
        try:
            note = await get_quick_note(note_id)
            if note is None:
                logger.warning("随手记不存在", note_id=note_id)
                return False

            await _update_processing_status(note_id, "processing")

            # Step 1: Completeness check
            is_meaningful = await _check_completeness(note.content)
            if not is_meaningful:
                logger.info("随手记内容不完整，跳过处理", note_id=note_id)
                await _update_processing_status(note_id, "skipped")
                return True

            # Step 2: Signal extraction
            signals = await extract_signals(note.content, "quicknote", note_id)
            logger.info("信号提取完成", note_id=note_id, signal_count=len(signals))

            # Step 3: Profile update (if signals found)
            if signals:
                from app.services.profile_builder import update_existing_profiles, save_profile
                new_fragments = await update_existing_profiles(signals)
                for fragment in new_fragments:
                    await save_profile(fragment)
                logger.info("画像更新完成", note_id=note_id, fragment_count=len(new_fragments))

            await _update_processing_status(note_id, "completed")
            return True

        except Exception:
            if attempt < max_retries:
                wait_seconds = 5 * (2 ** attempt)
                logger.warning(
                    "随手记处理失败，即将重试",
                    note_id=note_id,
                    attempt=attempt + 1,
                    retry_in_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.exception("随手记处理最终失败", note_id=note_id)
                await _update_processing_status(note_id, "failed")
                return False


# ═══════════════════════════════════════════
# Expense Record CRUD
# ═══════════════════════════════════════════

async def create_expense_record(
    amount: float,
    category: str,
    description: str = "",
    note: str | None = None,
    expense_date: str = "",
) -> ExpenseRecord:
    record_id = uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not expense_date:
        expense_date = datetime.now().strftime("%Y-%m-%d")

    async with get_connection() as db:
        await db.execute(
            "INSERT INTO expense_records (id, amount, category, description, note, expense_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (record_id, amount, category, description, note, expense_date, now),
        )
        await db.commit()

    return ExpenseRecord(
        id=record_id,
        amount=amount,
        category=category,
        description=description,
        note=note,
        expense_date=expense_date,
        created_at=now,
    )


async def get_expense_record(record_id: str) -> ExpenseRecord | None:
    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM expense_records WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
    if row is None:
        return None
    return ExpenseRecord(
        id=row["id"],
        amount=row["amount"],
        category=row["category"],
        description=row["description"],
        note=row["note"],
        expense_date=row["expense_date"],
        created_at=row["created_at"],
    )


async def update_expense_record(record_id: str, **kwargs) -> ExpenseRecord | None:
    fields = []
    values = []
    for key in ("amount", "category", "description", "note", "expense_date"):
        if key in kwargs and kwargs[key] is not None:
            fields.append(f"{key} = ?")
            values.append(kwargs[key])
    if not fields:
        return await get_expense_record(record_id)
    values.append(record_id)
    async with get_connection() as db:
        await db.execute(
            f"UPDATE expense_records SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        await db.commit()
    return await get_expense_record(record_id)


async def delete_expense_record(record_id: str) -> None:
    async with get_connection() as db:
        await db.execute("DELETE FROM expense_records WHERE id = ?", (record_id,))
        await db.commit()


async def list_expense_records(
    expense_date: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ExpenseRecord]:
    conditions = []
    params = []
    if expense_date:
        conditions.append("expense_date = ?")
        params.append(expense_date)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if start_date:
        conditions.append("expense_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("expense_date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with get_connection() as db:
        cursor = await db.execute(
            f"SELECT * FROM expense_records {where} ORDER BY expense_date DESC, created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()
    return [
        ExpenseRecord(
            id=row["id"],
            amount=row["amount"],
            category=row["category"],
            description=row["description"],
            note=row["note"],
            expense_date=row["expense_date"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


async def get_expense_stats(start_date: str | None = None, end_date: str | None = None) -> dict:
    """获取消费统计：总金额、分类汇总、日趋势"""
    conditions = []
    params = []
    if start_date:
        conditions.append("expense_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("expense_date <= ?")
        params.append(end_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with get_connection() as db:
        # Total amount
        cursor = await db.execute(
            f"SELECT COALESCE(SUM(amount), 0) as total FROM expense_records {where}",
            params,
        )
        total_row = await cursor.fetchone()
        total_amount = total_row["total"] if total_row else 0

        # Category breakdown
        cursor = await db.execute(
            f"SELECT category, SUM(amount) as amount, COUNT(*) as count FROM expense_records {where} GROUP BY category ORDER BY amount DESC",
            params,
        )
        cat_rows = await cursor.fetchall()
        category_breakdown = []
        for row in cat_rows:
            pct = (row["amount"] / total_amount * 100) if total_amount > 0 else 0
            category_breakdown.append({
                "category": row["category"],
                "amount": round(row["amount"], 2),
                "count": row["count"],
                "percentage": round(pct, 1),
            })

        # Daily trend
        cursor = await db.execute(
            f"SELECT expense_date as date, SUM(amount) as amount FROM expense_records {where} GROUP BY expense_date ORDER BY expense_date",
            params,
        )
        daily_rows = await cursor.fetchall()
        daily_trend = [{"date": row["date"], "amount": round(row["amount"], 2)} for row in daily_rows]

    return {
        "total_amount": round(total_amount, 2),
        "category_breakdown": category_breakdown,
        "daily_trend": daily_trend,
    }
