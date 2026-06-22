from __future__ import annotations

import json
import re

from app.database import get_connection
from app.models.page import PageInput, PageUpdate, PageListItem, PageDetail, PageLink, TimelineEntry


def _fix_timestamp(timestamp: str, source_id: str, source_type: str, diary_dates: dict[str, str]) -> str:
    """For diary-sourced events, always use the diary date as timestamp.
    LLM may extract wrong dates (e.g. '2023-10-01' for a 2026 diary), so we
    only trust the actual diary date."""
    if source_type == "diary" and source_id in diary_dates:
        return diary_dates[source_id]
    # Non-diary sources: keep original if it looks like a valid date
    if timestamp and re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', timestamp):
        return timestamp
    # Fallback to diary date if available
    return diary_dates.get(source_id, timestamp or "")


def _generate_slug(title: str) -> str:
    # Remove Chinese book title marks
    title = re.sub(r'[《》]', '', title)
    if re.search(r'[\u4e00-\u9fff]', title):
        return title
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


async def get_page_by_slug(slug: str) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM pages WHERE slug = ?", (slug,))
        row = await cursor.fetchone()
        if not row:
            return None

        page = dict(row)
        page_id = page["id"]

        try:
            page["frontmatter"] = json.loads(page.get("frontmatter", "{}"))
        except (json.JSONDecodeError, TypeError):
            page["frontmatter"] = {}

        # Query timeline_events related to this page slug
        page_slug = page["slug"]
        cursor = await db.execute(
            "SELECT * FROM timeline_events WHERE related_page_slugs IS NOT NULL ORDER BY timestamp DESC",
        )
        all_rows = await cursor.fetchall()

        # Filter in Python for exact slug match within comma-separated list or JSON array
        timeline_rows = []
        seen_keys = set()  # 去重：同一天+相似摘要视为重复
        for row in all_rows:
            raw_slugs = row["related_page_slugs"] or ""
            # Support both comma-separated string and JSON array formats
            if raw_slugs.startswith("["):
                try:
                    slugs = json.loads(raw_slugs)
                except (json.JSONDecodeError, TypeError):
                    slugs = [s.strip() for s in raw_slugs.split(",") if s.strip()]
            else:
                slugs = [s.strip() for s in raw_slugs.split(",") if s.strip()]
            if page_slug not in slugs:
                continue
            # 去重key：日期 + 摘要前50字符（忽略空格差异）
            ts_date = (row["timestamp"] or "")[:10]
            summary_norm = (row["summary"] or "")[:50].strip().replace(" ", "")
            dedup_key = f"{ts_date}|{summary_norm}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            timeline_rows.append(row)

        # Fix invalid timestamps by looking up diary dates
        source_ids = list(set(row["source_id"] for row in timeline_rows if row["source_type"] == "diary" and row["source_id"]))
        diary_dates: dict[str, str] = {}
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            date_rows = await db.execute(f"SELECT id, date FROM diaries WHERE id IN ({placeholders})", source_ids)
            for dr in await date_rows.fetchall():
                diary_dates[dr["id"]] = dr["date"]

        page["timeline"] = [
            {
                "id": row["id"],
                "timestamp": _fix_timestamp(row["timestamp"], row["source_id"], row["source_type"], diary_dates),
                "event_type": row["event_type"],
                "summary": row["summary"],
                "content": row["content"] if "content" in row.keys() else row["summary"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "sentiment": row["sentiment"],
                "importance_score": row["importance_score"],
                "is_milestone": bool(row["is_milestone"]),
                "is_confirmed": bool(row["is_confirmed"]) if "is_confirmed" in row.keys() else False,
            }
            for row in timeline_rows
        ]

        page["summary"] = page["summary"] if page.get("summary") else ""
        try:
            page["aliases"] = json.loads(page["aliases"]) if page.get("aliases") else []
        except (json.JSONDecodeError, TypeError):
            page["aliases"] = []

        cursor = await db.execute(
            """SELECT p.slug, p.title, p.type, l.link_type, l.confidence
               FROM links l JOIN pages p ON l.target_page_id = p.id
               WHERE l.source_page_id = ?""",
            (page_id,),
        )
        forward_links = [dict(row) for row in await cursor.fetchall()]
        page["forward_links"] = forward_links

        cursor = await db.execute(
            """SELECT p.slug, p.title, p.type, l.link_type, l.confidence
               FROM links l JOIN pages p ON l.source_page_id = p.id
               WHERE l.target_page_id = ?""",
            (page_id,),
        )
        back_links = [dict(row) for row in await cursor.fetchall()]
        page["back_links"] = back_links

        cursor = await db.execute("SELECT tag FROM tags WHERE page_id = ?", (page_id,))
        tags = [row["tag"] for row in await cursor.fetchall()]
        page["tags"] = tags

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM page_versions WHERE page_id = ?", (page_id,)
        )
        version_row = await cursor.fetchone()
        page["version_count"] = version_row["cnt"] if version_row else 0

        return page


async def list_pages(
    type: str = None,
    sort: str = "updated_at",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    allowed_sort = {"updated_at", "created_at", "title"}
    sort_column = sort if sort in allowed_sort else "updated_at"

    async with get_connection() as db:
        if type:
            cursor = await db.execute(
                f"""SELECT p.id, p.slug, p.type, p.title, p.summary, p.updated_at, p.created_at,
                           GROUP_CONCAT(t.tag, ',') as tags_concat
                    FROM pages p
                    LEFT JOIN tags t ON t.page_id = p.id
                    WHERE p.type = ?
                    GROUP BY p.id
                    ORDER BY p.{sort_column} DESC
                    LIMIT ? OFFSET ?""",
                (type, limit, offset),
            )
        else:
            cursor = await db.execute(
                f"""SELECT p.id, p.slug, p.type, p.title, p.summary, p.updated_at, p.created_at,
                           GROUP_CONCAT(t.tag, ',') as tags_concat
                    FROM pages p
                    LEFT JOIN tags t ON t.page_id = p.id
                    GROUP BY p.id
                    ORDER BY p.{sort_column} DESC
                    LIMIT ? OFFSET ?""",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            tags_str = d.get("tags_concat") or ""
            tag_list = [t for t in tags_str.split(",") if t] if tags_str else []
            result.append({
                "slug": d["slug"],
                "type": d["type"],
                "title": d["title"],
                "summary": d.get("summary", ""),
                "tags": tag_list,
                "updated_at": d.get("updated_at", ""),
                "created_at": d.get("created_at", ""),
            })
        return result


async def create_page(slug: str = None, data: PageInput = None) -> dict:
    if data is None:
        data = PageInput(title="")

    if slug is None:
        slug = _generate_slug(data.title)

    async with get_connection() as db:
        cursor = await db.execute("SELECT id FROM pages WHERE slug = ?", (slug,))
        if await cursor.fetchone():
            return {"error": "duplicate_slug", "slug": slug}

        timeline_json = json.dumps(
            [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in data.timeline],
            ensure_ascii=False,
        )
        frontmatter_json = json.dumps(data.frontmatter, ensure_ascii=False)

        summary = getattr(data, "summary", "") or ""
        aliases_raw = getattr(data, "aliases", []) or []
        aliases_json = json.dumps(aliases_raw, ensure_ascii=False) if not isinstance(aliases_raw, str) else aliases_raw

        cursor = await db.execute(
            """INSERT INTO pages (slug, type, title, frontmatter, compiled_truth, timeline, summary, aliases)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, data.type, data.title, frontmatter_json, data.compiled_truth, timeline_json, summary, aliases_json),
        )
        page_id = cursor.lastrowid

        if data.timeline:
            for entry in data.timeline:
                d = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
                tags_set = set()
                source_type = d.get("source_type", "")
                source_id = d.get("source_id", "")
                if source_type:
                    tags_set.add(f"source:{source_type}")
                if source_id:
                    tags_set.add(f"source_id:{source_id}")
                for tag in tags_set:
                    await db.execute(
                        "INSERT OR IGNORE INTO tags (page_id, tag) VALUES (?, ?)",
                        (page_id, tag),
                    )

        cursor = await db.execute(
            "INSERT INTO pages_fts(rowid, slug, title, compiled_truth) VALUES (?, ?, ?, ?)",
            (page_id, slug, data.title, data.compiled_truth),
        )

        await db.commit()

    # Parse links from compiled_truth and frontmatter
    from app.services.compiler import update_backlinks_for_page
    await update_backlinks_for_page(page_id, slug, data.compiled_truth, data.frontmatter)

    return await get_page_by_slug(slug)


async def update_page(slug: str, data: PageUpdate) -> dict | None:
    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM pages WHERE slug = ?", (slug,))
        row = await cursor.fetchone()
        if not row:
            return None

        existing = dict(row)

        updates = []
        values = []

        if data.compiled_truth is not None:
            updates.append("compiled_truth = ?")
            values.append(data.compiled_truth)

        if data.frontmatter is not None:
            updates.append("frontmatter = ?")
            values.append(json.dumps(data.frontmatter, ensure_ascii=False))

        if data.title is not None:
            updates.append("title = ?")
            values.append(data.title)

        if data.timeline_append is not None:
            try:
                existing_timeline = json.loads(existing.get("timeline", "[]"))
            except (json.JSONDecodeError, TypeError):
                existing_timeline = []
            for entry in data.timeline_append:
                d = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
                existing_timeline.append(d)
            updates.append("timeline = ?")
            values.append(json.dumps(existing_timeline, ensure_ascii=False))

        if data.summary is not None:
            updates.append("summary = ?")
            values.append(data.summary)

        if data.aliases is not None:
            updates.append("aliases = ?")
            values.append(json.dumps(data.aliases, ensure_ascii=False))

        if updates:
            updates.append("updated_at = datetime('now', 'localtime')")
            values.append(slug)
            await db.execute(
                f"UPDATE pages SET {', '.join(updates)} WHERE slug = ?",
                values,
            )
            await db.commit()

    # Re-parse links if compiled_truth or frontmatter changed
    if data.compiled_truth is not None or data.frontmatter is not None:
        from app.services.compiler import update_backlinks_for_page
        page = await get_page_by_slug(slug)
        if page:
            await update_backlinks_for_page(
                page["id"], slug,
                page.get("compiled_truth", ""),
                page.get("frontmatter", {}),
            )

    return await get_page_by_slug(slug)


async def delete_page(slug: str) -> bool:
    async with get_connection() as db:
        cursor = await db.execute("SELECT type FROM pages WHERE slug = ?", (slug,))
        row = await cursor.fetchone()
        if not row:
            return False
        if row["type"] == "system":
            return False

        await db.execute("DELETE FROM pages WHERE slug = ?", (slug,))
        await db.commit()
        return True


async def upsert_page(data: dict) -> str | None:
    slug = data.get("slug")
    if not slug:
        return None

    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM pages WHERE slug = ?", (slug,))
        row = await cursor.fetchone()

        if row:
            existing = dict(row)
            updates = []
            values = []

            if "compiled_truth" in data:
                updates.append("compiled_truth = ?")
                values.append(data["compiled_truth"])

            if "summary" in data:
                updates.append("summary = ?")
                values.append(data["summary"])

            if "aliases" in data:
                aliases_val = data["aliases"]
                aliases_json = json.dumps(aliases_val, ensure_ascii=False) if not isinstance(aliases_val, str) else aliases_val
                updates.append("aliases = ?")
                values.append(aliases_json)

            if "frontmatter" in data:
                fm_val = data["frontmatter"]
                fm_json = json.dumps(fm_val, ensure_ascii=False) if not isinstance(fm_val, str) else fm_val
                updates.append("frontmatter = ?")
                values.append(fm_json)

            if "timeline" in data:
                try:
                    existing_timeline = json.loads(existing.get("timeline", "[]"))
                except (json.JSONDecodeError, TypeError):
                    existing_timeline = []
                for entry in data["timeline"]:
                    d = entry.model_dump() if hasattr(entry, "model_dump") else entry
                    existing_timeline.append(d)
                updates.append("timeline = ?")
                values.append(json.dumps(existing_timeline, ensure_ascii=False))

            if updates:
                updates.append("updated_at = datetime('now', 'localtime')")
                values.append(slug)
                await db.execute(
                    f"UPDATE pages SET {', '.join(updates)} WHERE slug = ?",
                    values,
                )
                await db.commit()
        else:
            page_type = data.get("type", "concept")
            title = data.get("title", slug)
            compiled_truth = data.get("compiled_truth", "")
            summary = data.get("summary", "")
            aliases_raw = data.get("aliases", [])
            aliases_json = json.dumps(aliases_raw, ensure_ascii=False) if not isinstance(aliases_raw, str) else aliases_raw
            frontmatter = data.get("frontmatter", {})
            frontmatter_json = json.dumps(frontmatter, ensure_ascii=False)
            timeline = data.get("timeline", [])
            timeline_json = json.dumps(
                [e.model_dump() if hasattr(e, "model_dump") else e for e in timeline],
                ensure_ascii=False,
            )

            cursor = await db.execute(
                """INSERT INTO pages (slug, type, title, frontmatter, compiled_truth, timeline, summary, aliases)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (slug, page_type, title, frontmatter_json, compiled_truth, timeline_json, summary, aliases_json),
            )
            page_id = cursor.lastrowid

            await db.execute(
                "INSERT INTO pages_fts(rowid, slug, title, compiled_truth) VALUES (?, ?, ?, ?)",
                (page_id, slug, title, compiled_truth),
            )

            if timeline:
                for entry in timeline:
                    d = entry.model_dump() if hasattr(entry, "model_dump") else entry
                    tags_set = set()
                    source_type = d.get("source_type", "")
                    source_id = d.get("source_id", "")
                    if source_type:
                        tags_set.add(f"source:{source_type}")
                    if source_id:
                        tags_set.add(f"source_id:{source_id}")
                    for tag in tags_set:
                        await db.execute(
                            "INSERT OR IGNORE INTO tags (page_id, tag) VALUES (?, ?)",
                            (page_id, tag),
                        )

            await db.commit()

    # Parse links from compiled_truth and frontmatter
    from app.services.compiler import update_backlinks_for_page
    page = await get_page_by_slug(slug)
    if page:
        await update_backlinks_for_page(
            page["id"], slug,
            data.get("compiled_truth", page.get("compiled_truth", "")),
            data.get("frontmatter", page.get("frontmatter", {})),
        )

    return slug