from __future__ import annotations

import hashlib
import json
import struct
import os
from pathlib import Path

from app.database import get_connection
from app.config import settings
from app.utils.embedding import embed_texts
from app.services.gbrain_page import upsert_page


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith('---\n'):
        return {}, content
    parts = content.split('---\n', 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1]
    body = parts[2]
    fm = {}
    for line in fm_text.strip().split('\n'):
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            fm[key] = value
    return fm, body


def _pack_embedding(embedding: list[float]) -> bytes:
    return struct.pack(f'{len(embedding)}f', *embedding)


def _split_sentences(text: str) -> list[str]:
    import re
    sentences = re.split(r'(?<=[.!?。！？])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text.strip()] if text.strip() else []
    return sentences


def _chunk_sentences(sentences: list[str], target_words: int = 300, overlap_words: int = 50) -> list[str]:
    chunks = []
    i = 0
    current = []
    current_word_count = 0

    while i < len(sentences):
        s = sentences[i]
        s_words = len(s.split())

        if current_word_count + s_words <= target_words or not current:
            current.append(s)
            current_word_count += s_words
            i += 1
        else:
            chunks.append(' '.join(current))
            overlap_count = 0
            overlap_sentences = []
            for prev in reversed(current):
                prev_words = len(prev.split())
                if overlap_count + prev_words <= overlap_words:
                    overlap_sentences.insert(0, prev)
                    overlap_count += prev_words
                else:
                    break
            current = overlap_sentences
            current_word_count = overlap_count

    if current:
        chunks.append(' '.join(current))

    return chunks


async def ingest_directory(dir_path: str) -> dict:
    imported = 0
    skipped = 0
    errors: list[str] = []

    root = Path(dir_path)
    md_files = sorted(root.rglob('*.md'))

    async with get_connection() as db:
        for file_path in md_files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='replace')
            except Exception as e:
                errors.append(f"读取文件失败 {file_path}: {e}")
                continue

            sha256_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

            cursor = await db.execute(
                "SELECT sha256 FROM ingest_log WHERE file_path = ?",
                (str(file_path),),
            )
            existing = await cursor.fetchone()
            if existing and existing[0] == sha256_hash:
                skipped += 1
                continue

            fm, body = _parse_frontmatter(content)

            compiled_truth = body
            timeline = ""
            if '\n---\n' in body:
                parts = body.split('\n---\n', 1)
                compiled_truth = parts[0].strip()
                timeline = parts[1].strip() if len(parts) > 1 else ""

            slug = file_path.stem.lower().replace(' ', '-')

            page_type = fm.get('type') or 'source'
            title = fm.get('title') or file_path.stem

            try:
                page = await upsert_page(
                    db,
                    slug=slug,
                    page_type=page_type,
                    title=title,
                    frontmatter=fm,
                    compiled_truth=compiled_truth,
                    timeline=timeline,
                )
            except Exception as e:
                errors.append(f"创建页面失败 {file_path}: {e}")
                continue

            page_id = page["id"]

            sentences = _split_sentences(compiled_truth)
            chunks = _chunk_sentences(sentences)

            chunk_texts_for_embedding: list[str] = []
            chunk_data: list[tuple[int, str]] = []

            for idx, chunk_text in enumerate(chunks):
                if not chunk_text.strip():
                    continue
                chunk_data.append((idx, chunk_text))
                chunk_texts_for_embedding.append(chunk_text)

            embeddings: list[list[float]] = []
            if chunk_texts_for_embedding:
                try:
                    embeddings = await embed_texts(chunk_texts_for_embedding)
                except Exception as e:
                    errors.append(f"生成嵌入失败 {file_path}: {e}")
                    embeddings = []

            for (idx, chunk_text), embedding in zip(chunk_data, embeddings):
                emb_bytes = _pack_embedding(embedding)
                await db.execute(
                    "INSERT INTO content_chunks (page_id, chunk_text, embedding, chunk_index) VALUES (?, ?, ?, ?)",
                    (page_id, chunk_text, emb_bytes, idx),
                )

            await db.execute(
                "INSERT OR REPLACE INTO ingest_log (file_path, sha256, status, timestamp) VALUES (?, ?, 'imported', datetime('now', 'localtime'))",
                (str(file_path), sha256_hash),
            )

            imported += 1

    return {"imported": imported, "skipped": skipped, "errors": errors}


async def get_stats() -> dict:
    async with get_connection() as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM pages")
        row = await cursor.fetchone()
        total_pages = row[0] if row else 0

        cursor = await db.execute("SELECT type, COUNT(*) as cnt FROM pages GROUP BY type")
        rows = await cursor.fetchall()
        pages_by_type = {r[0]: r[1] for r in rows}

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM raw_signals")
        row = await cursor.fetchone()
        total_signals = row[0] if row else 0

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM raw_signals WHERE status = 'processed'")
        row = await cursor.fetchone()
        processed_signals = row[0] if row else 0

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM page_versions")
        row = await cursor.fetchone()
        total_versions = row[0] if row else 0

    return {
        "total_pages": total_pages,
        "pages_by_type": pages_by_type,
        "total_signals": total_signals,
        "unprocessed_signals": total_signals - processed_signals,
        "total_versions": total_versions,
    }