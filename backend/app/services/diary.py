from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

import structlog

from app.database import get_connection
from app.models.diary import Diary, DiarySearchResult
from app.prompts.diary_summary import DIARY_SUMMARY_PROMPT
from app.services.signal_extractor import extract_signals
from app.utils.llm import chat_completion, reset_token_counter, get_token_count

logger = structlog.get_logger()

# Global counter for diary processing sequence number
_diary_process_counter = 0
_TOKEN_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "token_usage.log"


def _log_token_usage(diary_date: str, token_count: int) -> None:
    """Append token usage for one diary to the log file."""
    global _diary_process_counter
    _diary_process_counter += 1
    try:
        _TOKEN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_TOKEN_LOG_FILE, "a", encoding="utf-8") as f:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{now}] 处理第{_diary_process_counter}篇日记（{diary_date}），本次处理消耗了{token_count}token\n")
    except Exception:
        logger.exception("写入token日志失败")


async def check_diary_duplicates(entries: list[dict]) -> list[dict]:
    """Check which entries are duplicates of existing diaries.
    Returns a list of {index, date, content_preview, existing_date, existing_id} for duplicates.
    Matches by content only (regardless of date).
    """
    duplicates = []
    async with get_connection() as db:
        for i, entry in enumerate(entries):
            date = entry.get("date", "")
            content = entry.get("content", "").strip()
            if not content:
                continue
            # Check by content only (ignore date)
            cursor = await db.execute(
                "SELECT id, date, content FROM diaries WHERE content = ?",
                (content,),
            )
            row = await cursor.fetchone()
            if row:
                duplicates.append({
                    "index": i,
                    "date": date,
                    "content_preview": content[:80] + ("..." if len(content) > 80 else ""),
                    "existing_id": row["id"],
                    "existing_date": row["date"],
                })
    return duplicates


async def create_diary(
    date: str,
    content: str,
    location: str | None = None,
    weather: str | None = None,
    temperature: str | None = None,
    humidity: str | None = None,
) -> Diary:
    diary_id = uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as db:
        await db.execute(
            "INSERT INTO diaries (id, date, content, location, weather, temperature, humidity, created_at, processing_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (diary_id, date, content, location, weather, temperature, humidity, now, "pending"),
        )
        await db.commit()

    return Diary(
        id=diary_id,
        date=date,
        content=content,
        location=location,
        weather=weather,
        temperature=temperature,
        humidity=humidity,
        created_at=now,
    )


async def get_diary(diary_id: str) -> Diary | None:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM diaries WHERE id = ?",
            (diary_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    return Diary(
        id=row["id"],
        date=row["date"],
        content=row["content"],
        extracted_summary=row["extracted_summary"],
        extracted_tags=row["extracted_tags"],
        chat_message_id=row["chat_message_id"],
        location=row["location"],
        weather=row["weather"],
        temperature=row["temperature"],
        humidity=row["humidity"],
        created_at=row["created_at"],
    )


async def update_diary(diary_id: str, content: str, date: str | None = None) -> Diary | None:
    async with get_connection() as db:
        if date:
            await db.execute(
                "UPDATE diaries SET content = ?, date = ? WHERE id = ?",
                (content, date, diary_id),
            )
        else:
            await db.execute(
                "UPDATE diaries SET content = ? WHERE id = ?",
                (content, diary_id),
            )
        await db.commit()
    return await get_diary(diary_id)


async def delete_diary(diary_id: str) -> None:
    async with get_connection() as db:
        await db.execute("DELETE FROM diaries WHERE id = ?", (diary_id,))
        await db.execute("DELETE FROM diaries_fts WHERE id = ?", (diary_id,))
        await db.execute("DELETE FROM timeline_events WHERE source_id = ?", (diary_id,))
        await db.commit()


async def list_diaries(limit: int = 20, offset: int = 0) -> list[Diary]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM diaries ORDER BY date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()

    return [
        Diary(
            id=row["id"],
            date=row["date"],
            content=row["content"],
            extracted_summary=row["extracted_summary"],
            extracted_tags=row["extracted_tags"],
            chat_message_id=row["chat_message_id"],
            location=row["location"],
            weather=row["weather"],
            temperature=row["temperature"],
            humidity=row["humidity"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


async def list_diary_dates() -> list[dict]:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, date FROM diaries ORDER BY date"
        )
        rows = await cursor.fetchall()
    return [{"id": row["id"], "date": row["date"]} for row in rows]


async def search_diaries(query: str, limit: int = 10) -> list[DiarySearchResult]:
    search_term = f"%{query}%"
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM diaries "
            "WHERE content LIKE ? OR extracted_summary LIKE ? OR extracted_tags LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (search_term, search_term, search_term, limit),
        )
        rows = await cursor.fetchall()

    return [
        DiarySearchResult(
            id=row["id"],
            date=row["date"],
            content=row["content"],
            extracted_summary=row["extracted_summary"],
            extracted_tags=row["extracted_tags"],
            location=row["location"],
            rank=0,
        )
        for row in rows
    ]


async def update_diary_summary(diary_id: str, summary: str, tags: str) -> None:
    async with get_connection() as db:
        await db.execute(
            "UPDATE diaries SET extracted_summary = ?, extracted_tags = ? WHERE id = ?",
            (summary, tags, diary_id),
        )
        await db.commit()


def _parse_summary_response(raw: str) -> tuple[str, str]:
    json_str = raw
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        obj_match = re.search(r"\{.*\}", json_str, re.DOTALL)
        if obj_match:
            try:
                data = json.loads(obj_match.group())
            except json.JSONDecodeError:
                return raw[:200], ""
        else:
            return raw[:200], ""

    summary = data.get("summary", "")
    tags_list = data.get("tags", [])
    tags = ",".join(tags_list) if isinstance(tags_list, list) else str(tags_list)

    return summary, tags


async def _cleanup_diary_events(diary_id: str) -> None:
    """Delete existing timeline events for a diary before re-processing, to avoid duplicates."""
    try:
        async with get_connection() as db:
            await db.execute(
                "DELETE FROM timeline_events WHERE source_type = 'diary' AND source_id = ?",
                (diary_id,),
            )
            await db.commit()
    except Exception:
        logger.exception("清理日记时间线事件失败", diary_id=diary_id)


async def _update_processing_status(diary_id: str, status: str) -> None:
    """更新日记处理状态：pending / processing / completed / failed"""
    try:
        async with get_connection() as db:
            await db.execute(
                "UPDATE diaries SET processing_status = ? WHERE id = ?",
                (status, diary_id),
            )
            await db.commit()
    except Exception:
        logger.exception("更新日记处理状态失败", diary_id=diary_id, status=status)


async def get_pending_diaries() -> list[dict]:
    """获取所有未处理完成的日记（pending 或 failed），用于中断恢复"""
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, date, processing_status FROM diaries WHERE processing_status IN ('pending', 'failed') ORDER BY created_at ASC",
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def retry_failed_diaries() -> dict:
    """重新处理所有失败的日记，用于中断恢复"""
    pending = await get_pending_diaries()
    retried = 0
    succeeded = 0
    failed = 0

    for entry in pending:
        # 标记为processing
        await _update_processing_status(entry["id"], "processing")
        success = await process_diary_async(entry["id"])
        if success:
            succeeded += 1
        else:
            failed += 1
        retried += 1

    return {
        "total": len(pending),
        "retried": retried,
        "succeeded": succeeded,
        "failed": failed,
    }


async def process_diary_async(diary_id: str, max_retries: int = 3) -> bool:
    """日记异步处理：摘要提取 → 标签生成 → 信号提取 → 时间线事件 → 画像更新 → 关系提取
    带指数退避重试逻辑，最多重试 max_retries 次。返回是否处理成功。
    """
    # Reset token counter at the start of each diary processing
    reset_token_counter()
    diary_date = ""

    for attempt in range(max_retries + 1):
        try:
            diary = await get_diary(diary_id)
            if diary is None:
                logger.warning("日记不存在", diary_id=diary_id)
                return False

            diary_date = diary.date

            # Clean up any existing timeline events for this diary to avoid duplicates on retry
            await _cleanup_diary_events(diary_id)

            # 动态计算摘要长度：最多为原文30%，目标约为上限的80%
            content_stripped = diary.content.strip()
            max_chars = round(len(content_stripped) * 0.30)
            target_chars = round(max_chars * 0.8)
            prompt = DIARY_SUMMARY_PROMPT.format(
                content=diary.content, date=diary.date,
                target_chars=target_chars, max_chars=max_chars,
            )
            raw = await chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=20000,
                purpose="日记摘要",
            )
            summary, tags = _parse_summary_response(raw)
            await update_diary_summary(diary_id, summary, tags)

            # 原文切片向量化写入 LanceDB（用于 RAG 原文向量检索）
            try:
                from app.utils.text_processing import split_long_text
                from app.services.vector_store import vector_store
                from app.utils.embedding import embed_texts

                # 重处理时先清理旧数据
                await vector_store.delete_diary_chunks(diary_id)
                chunks = split_long_text(diary.content, chunk_size=400, overlap=80)
                if chunks:
                    chunk_vectors = await embed_texts(chunks)
                    for idx, (chunk, vec) in enumerate(zip(chunks, chunk_vectors)):
                        await vector_store.add_diary_chunk(
                            chunk_id=f"{diary_id}_chunk_{idx}",
                            source_type="diary",
                            source_id=diary_id,
                            chunk_index=idx,
                            source_date=diary.date,
                            content=chunk,
                            vector=vec,
                        )
                    logger.info("原文向量切片写入完成", diary_id=diary_id, chunk_count=len(chunks))
            except Exception:
                logger.exception("原文向量切片写入失败", diary_id=diary_id)

            signals = await extract_signals(diary.content, "diary", diary_id)
            logger.info("信号提取完成", diary_id=diary_id, signal_count=len(signals))

            from app.services.timeline import extract_and_create_events, _build_event_context
            event_context = await _build_event_context(
                diary_summary=summary,
                diary_tags=tags,
                diary_date=diary.date,
            )
            events = await extract_and_create_events(
                diary.content, "diary", diary_id, source_date=diary.date, context=event_context,
            )
            logger.info("时间线事件提取完成", diary_id=diary_id, event_count=len(events))

            # Retry timeline extraction if empty (LLM may return empty due to transient issues)
            if not events and len(diary.content.strip()) >= 30:
                logger.warning("时间线事件提取为空，重试一次", diary_id=diary_id)
                events = await extract_and_create_events(
                    diary.content, "diary", diary_id, source_date=diary.date, context=event_context,
                )
                logger.info("时间线事件重试完成", diary_id=diary_id, event_count=len(events))

            if signals:
                from app.services.profile_builder import build_profiles_from_signals, save_profile, update_existing_profiles
                new_fragments = await update_existing_profiles(signals)
                for fragment in new_fragments:
                    await save_profile(fragment)
                logger.info("画像更新完成", diary_id=diary_id, fragment_count=len(new_fragments))

            try:
                from app.services.knowledge import extract_knowledge_from_diary
                kb_results = await extract_knowledge_from_diary(diary.content, diary_id=diary_id)
                logger.info("知识提取完成", diary_id=diary_id, entity_count=len(kb_results))
                # Retry knowledge extraction if empty (LLM may return empty due to transient issues)
                if not kb_results and len(diary.content.strip()) >= 30:
                    logger.warning("知识提取为空，重试一次", diary_id=diary_id)
                    kb_results = await extract_knowledge_from_diary(diary.content, diary_id=diary_id)
                    logger.info("知识提取重试完成", diary_id=diary_id, entity_count=len(kb_results))
            except Exception:
                logger.exception("日记知识提取失败", diary_id=diary_id)

            # Append to wiki log
            try:
                from app.services.compiler import append_wiki_log
                await append_wiki_log("ingest", f"diary/{diary_id} → 处理完成")
            except Exception:
                pass

            # Log token usage for this diary
            total_tokens = get_token_count()
            _log_token_usage(diary_date, total_tokens)
            logger.info("日记处理完成，token消耗", diary_id=diary_id, date=diary_date, tokens=total_tokens)

            # 标记处理成功
            await _update_processing_status(diary_id, "completed")

            return True

        except Exception:
            if attempt < max_retries:
                wait_seconds = 5 * (2 ** attempt)  # 指数退避: 5s, 10s, 20s
                logger.warning(
                    "日记处理失败，即将重试",
                    diary_id=diary_id,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    retry_in_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.exception(
                    "日记处理最终失败",
                    diary_id=diary_id,
                    attempts=max_retries + 1,
                )
                # 标记处理失败
                await _update_processing_status(diary_id, "failed")
                return False
