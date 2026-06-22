from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

from app.models.knowledge import SearchRequest, SearchRequestV2, IngestRequest, CompileRequest
from app.models.page import PageInput, PageUpdate
from app.services.gbrain_page import (
    get_page_by_slug,
    list_pages,
    create_page,
    update_page,
    delete_page,
    upsert_page,
)
from app.services.gbrain_search import hybrid_search, hybrid_search_v2
from app.services.gbrain_ingest import ingest_directory, get_stats
from app.services.gbrain_lint import lint_brain
from app.services.compiler import compile_entity_manual, start_compile_scheduler
from app.database import get_connection

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class MergeRequest(BaseModel):
    target_slug: str
    source_slugs: list[str]
    preview: bool = False


@router.post("/pages/merge")
async def api_merge_pages(req: MergeRequest):
    """Merge multiple source pages into a target page.
    If preview=True, return merge preview without executing."""
    target_slug = req.target_slug
    source_slugs = req.source_slugs

    if not source_slugs:
        raise HTTPException(status_code=400, detail="source_slugs 不能为空")
    if target_slug in source_slugs:
        raise HTTPException(status_code=400, detail="目标页面不能同时是源页面")

    # Load target page
    target_page = await get_page_by_slug(target_slug)
    if target_page is None:
        raise HTTPException(status_code=404, detail=f"目标页面 {target_slug} 不存在")

    # Load all source pages
    source_pages = []
    for slug in source_slugs:
        page = await get_page_by_slug(slug)
        if page is None:
            raise HTTPException(status_code=404, detail=f"源页面 {slug} 不存在")
        if page.get("type") == "system":
            raise HTTPException(status_code=403, detail=f"系统页面 {slug} 不可合并")
        source_pages.append(page)

    # --- Compute merge data (shared between preview and real merge) ---
    # 1. Merge aliases
    target_aliases = list(target_page.get("aliases") or [])
    for sp in source_pages:
        if sp["title"] not in target_aliases:
            target_aliases.append(sp["title"])
        for alias in (sp.get("aliases") or []):
            if alias not in target_aliases:
                target_aliases.append(alias)

    # 2. Merge tags
    target_tags = set(target_page.get("tags") or [])
    for sp in source_pages:
        for tag in (sp.get("tags") or []):
            target_tags.add(tag)

    # 3. Merge frontmatter
    target_fm = dict(target_page.get("frontmatter") or {})
    if isinstance(target_fm, str):
        target_fm = json.loads(target_fm)

    target_related = list(target_fm.get("related_entities") or [])
    target_related_slugs = set()
    for entry in target_related:
        m = re.match(r'\[\[(.+?)\]\]', entry)
        if m:
            ref = m.group(1)
            s = ref.split(':', 1)[1] if ':' in ref else ref
            target_related_slugs.add(s)

    for sp in source_pages:
        sp_fm = sp.get("frontmatter") or {}
        if isinstance(sp_fm, str):
            sp_fm = json.loads(sp_fm)
        for entry in (sp_fm.get("related_entities") or []):
            m = re.match(r'\[\[(.+?)\]\]', entry)
            if m:
                ref = m.group(1)
                s = ref.split(':', 1)[1] if ':' in ref else ref
                if s not in target_related_slugs and s != target_slug:
                    target_related.append(entry)
                    target_related_slugs.add(s)

    target_fm["related_entities"] = target_related

    # 4. Merge compiled_truth - use LLM to re-summarize instead of concatenation
    target_truth = target_page.get("compiled_truth") or ""
    source_truths = []
    for sp in source_pages:
        sp_truth = sp.get("compiled_truth") or ""
        if sp_truth.strip():
            source_truths.append({"title": sp["title"], "truth": sp_truth})

    if source_truths:
        # 有源页面的知识总结需要合并，用LLM重新总结
        all_truths = []
        if target_truth.strip():
            all_truths.append({"title": target_page.get("title", ""), "truth": target_truth})
        all_truths.extend(source_truths)

        try:
            from app.utils.llm import chat_completion
            # 构建合并prompt
            truths_text = ""
            for i, t in enumerate(all_truths):
                truths_text += f"\n### 来源{i+1}：{t['title']}\n{t['truth']}\n"

            merge_prompt = f"""你是一个知识合并专家。以下是关于同一个实体的多段知识总结，它们来自不同的来源。请将它们合并为一段连贯的知识总结，要求：
1. 去掉重复的内容，保留每段独特的意思
2. 合并相似描述，不要简单拼接
3. 保持客观、简洁的风格
4. 输出合并后的总结，不要添加额外说明

{truths_text}

合并后的知识总结："""

            merged_truth = await chat_completion(
                messages=[{"role": "user", "content": merge_prompt}],
                temperature=0.3,
                max_tokens=20000,
                purpose="知识合并",
            )
            target_truth = merged_truth.strip() if merged_truth else target_truth
        except Exception:
            # LLM调用失败时回退到拼接
            for st in source_truths:
                target_truth += f"\n\n---\n## 合并自：{st['title']}\n\n{st['truth']}"

    # 5. Merge timelines from source pages into target
    target_timeline = []
    try:
        target_timeline = json.loads(target_page.get("timeline") or "[]")
    except (json.JSONDecodeError, TypeError):
        target_timeline = []

    for sp in source_pages:
        try:
            source_timeline = json.loads(sp.get("timeline") or "[]")
        except (json.JSONDecodeError, TypeError):
            source_timeline = []
        target_timeline.extend(source_timeline)

    # Sort by date and deduplicate
    target_timeline.sort(key=lambda x: x.get("date", "") or x.get("timestamp", "") or "")
    seen = set()
    deduped_timeline = []
    for entry in target_timeline:
        key = f"{entry.get('date', '') or entry.get('timestamp', '')}:{entry.get('content', '') or entry.get('summary', '')}"
        if key not in seen:
            seen.add(key)
            deduped_timeline.append(entry)
    target_timeline = deduped_timeline

    # 6. Count timeline events that would be transferred
    merged_timeline_count = 0
    async with get_connection() as db:
        for sp in source_pages:
            source_slug = sp["slug"]
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM timeline_events WHERE related_page_slugs LIKE ?",
                (f"%{source_slug}%",),
            )
            row = await cursor.fetchone()
            merged_timeline_count += row["cnt"]

    # --- Preview mode: return computed data without writing ---
    if req.preview:
        return {
            "preview": True,
            "target": {"slug": target_slug, "title": target_page.get("title", "")},
            "sources": [{"slug": sp["slug"], "title": sp.get("title", "")} for sp in source_pages],
            "merged_aliases": target_aliases,
            "merged_tags": sorted(target_tags),
            "merged_compiled_truth": target_truth,
            "merged_timeline_count": merged_timeline_count,
            "conflicts": [],
        }

    # --- Real merge: execute ---

    # Save pre-merge snapshot for undo
    snapshot_id = uuid.uuid4().hex
    snapshot_data = {
        "target_page_before": {
            "compiled_truth": target_page.get("compiled_truth") or "",
            "summary": target_page.get("summary") or "",
            "aliases": target_page.get("aliases") or [],
            "frontmatter": target_page.get("frontmatter") or {},
            "timeline": target_page.get("timeline") or "[]",
            "merged_from": target_page.get("merged_from"),
        },
        "source_pages_before": [],
        "timeline_events_changes": [],  # {event_id, old_related_page_slugs}
        "links_changes": [],  # {link_id, old_source_page_id, old_target_page_id}
        "links_deleted": [],  # Links deleted during merge (not just updated)
        "content_chunks_deleted": [],  # Content chunks deleted with source pages
        "tags_before_target": [],  # tags that were on target page before merge
    }

    # Save source pages data before deletion
    for sp in source_pages:
        sp_copy = dict(sp)
        # Ensure frontmatter is serializable
        if isinstance(sp_copy.get("frontmatter"), str):
            try:
                sp_copy["frontmatter"] = json.loads(sp_copy["frontmatter"])
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(sp_copy.get("aliases"), str):
            try:
                sp_copy["aliases"] = json.loads(sp_copy["aliases"])
            except (json.JSONDecodeError, TypeError):
                pass
        snapshot_data["source_pages_before"].append(sp_copy)

    async with get_connection() as db:
        try:
            # 6. Build merged_from
            merged_from = list(source_slugs)
            existing_merged = target_page.get("merged_from")
            if existing_merged:
                if isinstance(existing_merged, str):
                    try:
                        existing_merged = json.loads(existing_merged)
                    except (json.JSONDecodeError, TypeError):
                        existing_merged = [s.strip() for s in existing_merged.split(",") if s.strip()]
                if isinstance(existing_merged, list):
                    for s in existing_merged:
                        if s not in merged_from:
                            merged_from.append(s)

            # 7. Update target page (including merged timeline)
            aliases_json = json.dumps(target_aliases, ensure_ascii=False)
            fm_json = json.dumps(target_fm, ensure_ascii=False)
            timeline_json = json.dumps(target_timeline, ensure_ascii=False)

            await db.execute(
                "UPDATE pages SET compiled_truth=?, aliases=?, frontmatter=?, merged_from=?, timeline=?, updated_at=datetime('now','localtime') WHERE slug=?",
                (target_truth, aliases_json, fm_json, json.dumps(merged_from, ensure_ascii=False), timeline_json, target_slug),
            )

            # 7.5 Rewrite summary based on merged timeline (from timeline_events table)
            try:
                # Query timeline_events that now point to target slug
                tl_cursor = await db.execute(
                    "SELECT timestamp, summary FROM timeline_events WHERE related_page_slugs LIKE ? ORDER BY timestamp DESC LIMIT 50",
                    (f"%{target_slug}%",),
                )
                tl_rows = await tl_cursor.fetchall()
                if tl_rows:
                    timeline_lines = []
                    for tl_row in tl_rows:
                        ts = tl_row["timestamp"] or ""
                        summary = tl_row["summary"] or ""
                        if ts and summary:
                            timeline_lines.append(f"- {ts[:10]}: {summary}")
                    timeline_text = "\n".join(timeline_lines[:50])

                    summary_prompt = f"""基于以下时间线事件，为实体"{target_page.get('title', target_slug)}"写一段≤200字的摘要。
摘要应从用户视角总结与此实体的关系、互动模式和影响，禁止概念性解释。

时间线事件：
{timeline_text}

请直接输出摘要内容，不要添加标题或格式。"""

                    from app.utils.llm import chat_completion
                    summary_result = await chat_completion(
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.3,
                        max_tokens=20000,
                        purpose="合并后摘要重写",
                    )
                    new_summary = summary_result.strip() if summary_result else ""
                    if new_summary:
                        await db.execute(
                            "UPDATE pages SET summary=? WHERE slug=?",
                            (new_summary, target_slug),
                        )
            except Exception:
                pass

            # 8. Update tags for target page
            target_page_id = target_page["id"]

            # Save target page tags before merge
            cursor = await db.execute("SELECT tag FROM tags WHERE page_id = ?", (target_page_id,))
            tags_before = [row["tag"] for row in await cursor.fetchall()]
            snapshot_data["tags_before_target"] = tags_before

            await db.execute("DELETE FROM tags WHERE page_id = ?", (target_page_id,))
            for tag in target_tags:
                await db.execute("INSERT OR IGNORE INTO tags (page_id, tag) VALUES (?, ?)", (target_page_id, tag))

            # 9. Update timeline_events
            for sp in source_pages:
                source_slug = sp["slug"]
                cursor = await db.execute(
                    "SELECT id, related_page_slugs FROM timeline_events WHERE related_page_slugs LIKE ?",
                    (f"%{source_slug}%",),
                )
                rows = await cursor.fetchall()
                for row in rows:
                    old_slugs_str = row["related_page_slugs"] or ""
                    # Record change for undo
                    snapshot_data["timeline_events_changes"].append({
                        "event_id": row["id"],
                        "old_related_page_slugs": old_slugs_str,
                    })
                    try:
                        old_slugs = json.loads(old_slugs_str) if old_slugs_str.startswith("[") else [s.strip() for s in old_slugs_str.split(",") if s.strip()]
                    except (json.JSONDecodeError, TypeError):
                        old_slugs = [s.strip() for s in old_slugs_str.split(",") if s.strip()]

                    new_slugs = []
                    for s in old_slugs:
                        if s == source_slug:
                            if target_slug not in new_slugs:
                                new_slugs.append(target_slug)
                        else:
                            if s not in new_slugs:
                                new_slugs.append(s)
                    new_slugs_str = ",".join(new_slugs)
                    await db.execute(
                        "UPDATE timeline_events SET related_page_slugs = ? WHERE id = ?",
                        (new_slugs_str, row["id"]),
                    )

            # 9.5 Save links that will be deleted during merge
            source_ids = [sp["id"] for sp in source_pages]
            source_id_placeholders = ",".join("?" for _ in source_ids)

            # Links from source pages to target page (cascade-deleted when source pages are deleted)
            cursor = await db.execute(
                f"SELECT source_page_id, target_page_id, link_type, confidence FROM links WHERE source_page_id IN ({source_id_placeholders}) AND target_page_id = ?",
                source_ids + [target_page_id],
            )
            for row in await cursor.fetchall():
                snapshot_data["links_deleted"].append({
                    "source_page_id": row["source_page_id"],
                    "target_page_id": row["target_page_id"],
                    "link_type": row["link_type"],
                    "confidence": row["confidence"],
                })

            # Links from target page to source pages (cascade-deleted when source pages are deleted)
            cursor = await db.execute(
                f"SELECT source_page_id, target_page_id, link_type, confidence FROM links WHERE source_page_id = ? AND target_page_id IN ({source_id_placeholders})",
                [target_page_id] + source_ids,
            )
            for row in await cursor.fetchall():
                snapshot_data["links_deleted"].append({
                    "source_page_id": row["source_page_id"],
                    "target_page_id": row["target_page_id"],
                    "link_type": row["link_type"],
                    "confidence": row["confidence"],
                })

            # Links between source pages (become self-referencing after transfer, deleted by step 3)
            if len(source_ids) > 1:
                cursor = await db.execute(
                    f"SELECT source_page_id, target_page_id, link_type, confidence FROM links WHERE source_page_id IN ({source_id_placeholders}) AND target_page_id IN ({source_id_placeholders}) AND source_page_id != target_page_id",
                    source_ids + source_ids,
                )
                for row in await cursor.fetchall():
                    snapshot_data["links_deleted"].append({
                        "source_page_id": row["source_page_id"],
                        "target_page_id": row["target_page_id"],
                        "link_type": row["link_type"],
                        "confidence": row["confidence"],
                    })

            # Self-referencing source page links (updated then cascade-deleted)
            for sp_id in source_ids:
                cursor = await db.execute(
                    "SELECT source_page_id, target_page_id, link_type, confidence FROM links WHERE source_page_id = ? AND target_page_id = ?",
                    (sp_id, sp_id),
                )
                for row in await cursor.fetchall():
                    snapshot_data["links_deleted"].append({
                        "source_page_id": row["source_page_id"],
                        "target_page_id": row["target_page_id"],
                        "link_type": row["link_type"],
                        "confidence": row["confidence"],
                    })

            # 10. Transfer links
            for sp in source_pages:
                sp_id = sp["id"]
                # Record links before transfer for undo
                cursor = await db.execute(
                    "SELECT id, source_page_id, target_page_id FROM links WHERE source_page_id = ? AND target_page_id != ?",
                    (sp_id, target_page_id),
                )
                for link_row in await cursor.fetchall():
                    snapshot_data["links_changes"].append({
                        "link_id": link_row["id"],
                        "old_source_page_id": link_row["source_page_id"],
                        "old_target_page_id": link_row["target_page_id"],
                    })
                cursor = await db.execute(
                    "SELECT id, source_page_id, target_page_id FROM links WHERE target_page_id = ? AND source_page_id != ?",
                    (sp_id, target_page_id),
                )
                for link_row in await cursor.fetchall():
                    snapshot_data["links_changes"].append({
                        "link_id": link_row["id"],
                        "old_source_page_id": link_row["source_page_id"],
                        "old_target_page_id": link_row["target_page_id"],
                    })

                await db.execute(
                    "UPDATE links SET source_page_id = ? WHERE source_page_id = ? AND target_page_id != ?",
                    (target_page_id, sp_id, target_page_id),
                )
                await db.execute(
                    "UPDATE links SET target_page_id = ? WHERE target_page_id = ? AND source_page_id != ?",
                    (target_page_id, sp_id, target_page_id),
                )
                await db.execute(
                    "DELETE FROM links WHERE source_page_id = ? AND target_page_id = ?",
                    (target_page_id, target_page_id),
                )

            # 10.5 Save content_chunks for source pages before deletion
            for sp in source_pages:
                cursor = await db.execute(
                    "SELECT page_id, chunk_text, embedding, chunk_index FROM content_chunks WHERE page_id = ?",
                    (sp["id"],),
                )
                for chunk_row in await cursor.fetchall():
                    chunk_data = {
                        "page_id": chunk_row["page_id"],
                        "chunk_text": chunk_row["chunk_text"],
                        "chunk_index": chunk_row["chunk_index"],
                    }
                    if chunk_row["embedding"] is not None:
                        chunk_data["embedding"] = chunk_row["embedding"].hex()
                    else:
                        chunk_data["embedding"] = None
                    snapshot_data["content_chunks_deleted"].append(chunk_data)

            # 11. Delete source pages
            for sp in source_pages:
                await db.execute("DELETE FROM pages WHERE slug = ?", (sp["slug"],))

            # 11.5 Delete FTS entries for source pages
            for sp in source_pages:
                await db.execute("DELETE FROM pages_fts WHERE rowid = ?", (sp["id"],))

            # 12. Update FTS
            await db.execute(
                "UPDATE pages_fts SET compiled_truth=? WHERE rowid=(SELECT rowid FROM pages WHERE slug=?)",
                (target_truth, target_slug),
            )

            # 13. Save merge snapshot for undo
            await db.execute(
                "INSERT INTO merge_snapshots (id, target_slug, source_slugs, snapshot_data) VALUES (?, ?, ?, ?)",
                (snapshot_id, target_slug, json.dumps(source_slugs, ensure_ascii=False), json.dumps(snapshot_data, ensure_ascii=False)),
            )

            await db.commit()

        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"合并失败: {str(e)}")

    # Re-parse backlinks for target page
    from app.services.compiler import update_backlinks_for_page
    updated_page = await get_page_by_slug(target_slug)
    if updated_page:
        await update_backlinks_for_page(
            updated_page["id"], target_slug,
            updated_page.get("compiled_truth", ""),
            updated_page.get("frontmatter", {}),
        )

    # Note: compile_entity_manual is skipped here because:
    # 1. compiled_truth was already merged via LLM in step 4
    # 2. summary was already rewritten based on timeline in step 7.5
    # 3. compile_entity_manual depends on signals, not timeline, and may overwrite our merge results

    # Log the merge
    from app.services.compiler import append_wiki_log
    await append_wiki_log("merge", f"将 {', '.join(source_slugs)} 合并到 {target_slug}")

    result = await get_page_by_slug(target_slug)
    if result:
        result["merge_snapshot_id"] = snapshot_id
    return result


class UndoMergeRequest(BaseModel):
    snapshot_id: str


@router.post("/pages/merge/undo")
async def api_undo_merge(req: UndoMergeRequest):
    """Undo a merge operation using the saved snapshot."""
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM merge_snapshots WHERE id = ?", (req.snapshot_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合并快照不存在，无法撤回")

        snapshot = json.loads(row["snapshot_data"])
        target_slug = row["target_slug"]

        try:
            # 1. Restore target page to pre-merge state
            target_before = snapshot["target_page_before"]
            await db.execute(
                "UPDATE pages SET compiled_truth=?, summary=?, aliases=?, frontmatter=?, timeline=?, merged_from=?, updated_at=datetime('now','localtime') WHERE slug=?",
                (
                    target_before["compiled_truth"],
                    target_before["summary"],
                    json.dumps(target_before["aliases"], ensure_ascii=False),
                    json.dumps(target_before["frontmatter"], ensure_ascii=False),
                    target_before["timeline"],
                    json.dumps(target_before["merged_from"], ensure_ascii=False) if target_before["merged_from"] else None,
                    target_slug,
                ),
            )

            # 2. Restore target page tags
            cursor2 = await db.execute("SELECT id FROM pages WHERE slug = ?", (target_slug,))
            target_page_row = await cursor2.fetchone()
            if target_page_row:
                target_page_id = target_page_row["id"]
                await db.execute("DELETE FROM tags WHERE page_id = ?", (target_page_id,))
                for tag in snapshot.get("tags_before_target", []):
                    await db.execute("INSERT OR IGNORE INTO tags (page_id, tag) VALUES (?, ?)", (target_page_id, tag))

            # 3. Recreate source pages
            for sp_data in snapshot["source_pages_before"]:
                # Check if page already exists (shouldn't, but be safe)
                cursor2 = await db.execute("SELECT id FROM pages WHERE slug = ?", (sp_data["slug"],))
                if await cursor2.fetchone():
                    continue

                sp_aliases = sp_data.get("aliases", [])
                if isinstance(sp_aliases, list):
                    sp_aliases_json = json.dumps(sp_aliases, ensure_ascii=False)
                else:
                    sp_aliases_json = sp_aliases

                sp_frontmatter = sp_data.get("frontmatter", {})
                if isinstance(sp_frontmatter, dict):
                    sp_fm_json = json.dumps(sp_frontmatter, ensure_ascii=False)
                else:
                    sp_fm_json = sp_frontmatter

                sp_timeline = sp_data.get("timeline", "[]")
                if isinstance(sp_timeline, list):
                    sp_timeline_json = json.dumps(sp_timeline, ensure_ascii=False)
                else:
                    sp_timeline_json = sp_timeline

                await db.execute(
                    """INSERT INTO pages (id, slug, type, title, frontmatter, compiled_truth, timeline, summary, aliases, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))""",
                    (
                        sp_data["id"], sp_data["slug"], sp_data["type"], sp_data["title"],
                        sp_fm_json, sp_data.get("compiled_truth") or "", sp_timeline_json,
                        sp_data.get("summary") or "", sp_aliases_json, sp_data.get("created_at", ""),
                    ),
                )

                # Recreate FTS entry (delete first to avoid duplicate rowid)
                await db.execute("DELETE FROM pages_fts WHERE rowid = ?", (sp_data["id"],))
                await db.execute(
                    "INSERT INTO pages_fts (rowid, slug, title, compiled_truth) VALUES (?, ?, ?, ?)",
                    (sp_data["id"], sp_data["slug"], sp_data["title"], sp_data.get("compiled_truth") or ""),
                )

                # Recreate source page tags
                sp_tags = (sp_data.get("frontmatter", {}) if isinstance(sp_data.get("frontmatter"), dict) else {}).get("tags", [])
                if isinstance(sp_tags, str):
                    sp_tags = [t.strip() for t in sp_tags.split(",") if t.strip()]
                for tag in sp_tags:
                    await db.execute("INSERT OR IGNORE INTO tags (page_id, tag) VALUES (?, ?)", (sp_data["id"], tag))

            # 3.5 Restore content_chunks for source pages
            for chunk_data in snapshot.get("content_chunks_deleted", []):
                embedding = None
                if chunk_data.get("embedding") is not None:
                    embedding = bytes.fromhex(chunk_data["embedding"])
                await db.execute(
                    "INSERT INTO content_chunks (page_id, chunk_text, embedding, chunk_index) VALUES (?, ?, ?, ?)",
                    (chunk_data["page_id"], chunk_data["chunk_text"], embedding, chunk_data["chunk_index"]),
                )

            # 4. Restore timeline_events related_page_slugs
            for change in snapshot.get("timeline_events_changes", []):
                await db.execute(
                    "UPDATE timeline_events SET related_page_slugs = ? WHERE id = ?",
                    (change["old_related_page_slugs"], change["event_id"]),
                )

            # 5. Restore links
            for change in snapshot.get("links_changes", []):
                await db.execute(
                    "UPDATE links SET source_page_id = ?, target_page_id = ? WHERE id = ?",
                    (change["old_source_page_id"], change["old_target_page_id"], change["link_id"]),
                )

            # 5.5 Re-insert links that were deleted during merge
            for link_data in snapshot.get("links_deleted", []):
                await db.execute(
                    "INSERT INTO links (source_page_id, target_page_id, link_type, confidence) VALUES (?, ?, ?, ?)",
                    (link_data["source_page_id"], link_data["target_page_id"], link_data["link_type"], link_data["confidence"]),
                )

            # 6. Update FTS for target page
            if target_page_row:
                await db.execute(
                    "UPDATE pages_fts SET compiled_truth=? WHERE rowid=?",
                    (target_before["compiled_truth"], target_page_row["id"]),
                )

            # 7. Delete the snapshot
            await db.execute("DELETE FROM merge_snapshots WHERE id = ?", (req.snapshot_id,))

            await db.commit()

        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"撤回失败: {str(e)}")

    # Re-parse backlinks for target page
    from app.services.compiler import update_backlinks_for_page
    updated_page = await get_page_by_slug(target_slug)
    if updated_page:
        await update_backlinks_for_page(
            updated_page["id"], target_slug,
            updated_page.get("compiled_truth", ""),
            updated_page.get("frontmatter", {}),
        )

    # Log the undo
    from app.services.compiler import append_wiki_log
    await append_wiki_log("merge_undo", f"撤回合并：{row['source_slugs']} → {target_slug}")

    return {"ok": True, "message": "合并已撤回", "target_slug": target_slug}


@router.get("/pages")
async def api_list_pages(
    type: str = Query(default=None),
    sort: str = Query(default="updated_at"),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
):
    try:
        items = await list_pages(type=type, sort=sort, limit=limit, offset=offset)
        return {"items": items, "total": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{slug}")
async def api_get_page(slug: str):
    page = await get_page_by_slug(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="页面不存在")
    return page


@router.put("/pages/{slug}")
async def api_update_page(slug: str, data: PageUpdate):
    result = await update_page(slug, data)
    if result is None:
        raise HTTPException(status_code=404, detail="页面不存在")
    return result


@router.post("/pages")
async def api_create_page(data: PageInput):
    slug = data.slug or None
    result = await create_page(slug=slug, data=data)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=409, detail="页面已存在")
    return result


@router.delete("/pages/{slug}")
async def api_delete_page(slug: str):
    success = await delete_page(slug)
    if not success:
        raise HTTPException(status_code=403, detail="系统页面不可删除")
    return {"status": "deleted"}


@router.post("/search")
async def api_search(req: SearchRequestV2):
    """Hybrid search with mode toggle"""
    try:
        sources_param = req.sources if req.sources else None
        results = await hybrid_search_v2(
            query=req.query,
            mode=req.mode,
            limit=req.limit,
            sources=sources_param,
            rerank_enabled=req.rerank,
            graph_enabled=req.graph,
        )
        return {"results": results, "mode": req.mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/search")
async def api_search_get(
    q: str = Query(..., description="搜索关键词"),
    mode: str = Query(default="hybrid", description="搜索模式: hybrid, vector, graph, fts"),
    limit: int = Query(default=10, description="返回结果数量"),
):
    """Hybrid search via GET (convenience endpoint for simple queries)"""
    try:
        results = await hybrid_search_v2(
            query=q,
            mode=mode,
            limit=limit,
        )
        return {"results": results, "mode": mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {str(e)}")


@router.get("/backlinks")
async def api_backlinks_index():
    """Get all backlinks as a centralized index"""
    async with get_connection() as db:
        cursor = await db.execute(
            """SELECT p.slug as target_slug, p.title as target_title,
                      sp.slug as source_slug, sp.title as source_title, sp.type as source_type,
                      l.link_type, l.confidence
               FROM links l
               JOIN pages p ON l.target_page_id = p.id
               JOIN pages sp ON l.source_page_id = sp.id"""
        )
        rows = await cursor.fetchall()
        index: dict = {}
        for row in rows:
            target = row["target_slug"]
            if target not in index:
                index[target] = []
            index[target].append({
                "source_slug": row["source_slug"],
                "source_title": row["source_title"],
                "source_type": row["source_type"],
                "link_type": row["link_type"],
                "confidence": row["confidence"],
            })
        return index


@router.get("/backlinks/{slug}")
async def api_backlinks_for_slug(slug: str):
    """Get backlinks for a specific page"""
    async with get_connection() as db:
        cursor = await db.execute("SELECT id FROM pages WHERE slug = ?", (slug,))
        page = await cursor.fetchone()
        if not page:
            raise HTTPException(status_code=404, detail="页面不存在")
        page_id = page["id"]

        cursor = await db.execute(
            """SELECT sp.slug, sp.title, sp.type, l.link_type, l.confidence
               FROM links l
               JOIN pages sp ON l.source_page_id = sp.id
               WHERE l.target_page_id = ?""",
            (page_id,),
        )
        rows = await cursor.fetchall()
        return {
            "slug": slug,
            "backlinks": [
                {
                    "source_slug": row["slug"],
                    "source_title": row["title"],
                    "source_type": row["type"],
                    "link_type": row["link_type"],
                    "confidence": row["confidence"],
                }
                for row in rows
            ],
        }


@router.get("/graph")
async def api_knowledge_graph(
    type: str = Query(default=None),
    slug: str = Query(default=None),
    depth: int = Query(default=1),
):
    """Get knowledge graph data (nodes + edges)"""
    async with get_connection() as db:
        if slug:
            # Subgraph around a specific entity
            cursor = await db.execute("SELECT id, slug, title, type FROM pages WHERE slug = ?", (slug,))
            seed = await cursor.fetchone()
            if not seed:
                raise HTTPException(status_code=404, detail="页面不存在")

            visited_ids = {seed["id"]}
            current_ids = {seed["id"]}
            all_nodes = [dict(seed)]
            all_edges = []

            for d in range(depth):
                next_ids = set()
                ph = ",".join("?" for _ in current_ids)
                # Find links from/to current nodes
                cursor = await db.execute(
                    f"""SELECT l.source_page_id, l.target_page_id, l.link_type, l.confidence
                        FROM links l
                        WHERE l.source_page_id IN ({ph}) OR l.target_page_id IN ({ph})""",
                    list(current_ids) + list(current_ids),
                )
                link_rows = await cursor.fetchall()
                for lr in link_rows:
                    src_id = lr["source_page_id"]
                    tgt_id = lr["target_page_id"]
                    all_edges.append({
                        "source_page_id": src_id,
                        "target_page_id": tgt_id,
                        "link_type": lr["link_type"],
                        "confidence": lr["confidence"],
                    })
                    for nid in (src_id, tgt_id):
                        if nid not in visited_ids:
                            next_ids.add(nid)
                            visited_ids.add(nid)
                current_ids = next_ids

            # Fetch node details for all visited
            if visited_ids:
                ph = ",".join("?" for _ in visited_ids)
                cursor = await db.execute(
                    f"SELECT id, slug, title, type FROM pages WHERE id IN ({ph})",
                    list(visited_ids),
                )
                all_nodes = [dict(r) for r in await cursor.fetchall()]

            # Build slug-based edges
            id_to_slug = {n["id"]: n["slug"] for n in all_nodes}
            edges = []
            for e in all_edges:
                src_slug = id_to_slug.get(e["source_page_id"])
                tgt_slug = id_to_slug.get(e["target_page_id"])
                if src_slug and tgt_slug:
                    edges.append({
                        "source": src_slug,
                        "target": tgt_slug,
                        "link_type": e["link_type"],
                        "confidence": e["confidence"],
                    })

            return {"nodes": all_nodes, "edges": edges}

        else:
            # Full graph or filtered by type
            if type:
                cursor = await db.execute(
                    "SELECT id, slug, title, type FROM pages WHERE type = ?", (type,)
                )
            else:
                cursor = await db.execute("SELECT id, slug, title, type FROM pages")
            nodes = [dict(r) for r in await cursor.fetchall()]

            node_ids = {n["id"] for n in nodes}
            if not node_ids:
                return {"nodes": [], "edges": []}

            ph = ",".join("?" for _ in node_ids)
            cursor = await db.execute(
                f"""SELECT l.source_page_id, l.target_page_id, l.link_type, l.confidence
                    FROM links l
                    WHERE l.source_page_id IN ({ph}) AND l.target_page_id IN ({ph})""",
                list(node_ids) + list(node_ids),
            )
            link_rows = await cursor.fetchall()

            id_to_slug = {n["id"]: n["slug"] for n in nodes}
            edges = []
            for lr in link_rows:
                src_slug = id_to_slug.get(lr["source_page_id"])
                tgt_slug = id_to_slug.get(lr["target_page_id"])
                if src_slug and tgt_slug:
                    edges.append({
                        "source": src_slug,
                        "target": tgt_slug,
                        "link_type": lr["link_type"],
                        "confidence": lr["confidence"],
                    })

            return {"nodes": nodes, "edges": edges}


@router.post("/ingest")
async def api_ingest(request: IngestRequest):
    result = await ingest_directory(request.directory)
    return result


@router.get("/health")
async def api_health():
    report = await lint_brain()
    return report


@router.get("/stats")
async def api_stats():
    stats = await get_stats()
    return stats


@router.post("/compile")
async def api_compile(request: CompileRequest):
    result = await compile_entity_manual(request.entity_tag)
    return result


@router.post("/profile/weekly")
async def api_generate_weekly_profile():
    """Generate weekly profile."""
    from app.services.compiler import generate_weekly_profile
    result = await generate_weekly_profile()
    return result


@router.get("/profile/weekly")
async def api_get_weekly_profile():
    """Get the current weekly profile from pages table."""
    from datetime import datetime, timedelta
    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())
    week_key = week_start.strftime("%Y%W")
    slug = f"weekly_profile_{week_key}"
    page = await get_page_by_slug(slug)
    if page is None:
        return {"compiled_truth": "", "title": "", "updated_at": "", "slug": slug, "versions": []}
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, version_number, compiled_truth_snapshot, created_at "
            "FROM page_versions WHERE page_id = ? ORDER BY version_number DESC",
            (page["id"],),
        )
        versions = [dict(r) for r in await cursor.fetchall()]
    return {
        "compiled_truth": page.get("compiled_truth") or "",
        "title": page.get("title") or "",
        "updated_at": page.get("updated_at") or "",
        "slug": slug,
        "versions": versions,
    }


@router.post("/profile/monthly")
async def api_generate_monthly_profile():
    """Generate monthly profile."""
    from app.services.compiler import generate_monthly_profile
    result = await generate_monthly_profile()
    return result


@router.get("/profile/monthly")
async def api_get_monthly_profile():
    """Get the current monthly profile from pages table."""
    from datetime import datetime
    month_key = datetime.now().strftime("%Y%m")
    slug = f"monthly_profile_{month_key}"
    page = await get_page_by_slug(slug)
    if page is None:
        return {"compiled_truth": "", "title": "", "updated_at": "", "slug": slug, "versions": []}
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, version_number, compiled_truth_snapshot, created_at "
            "FROM page_versions WHERE page_id = ? ORDER BY version_number DESC",
            (page["id"],),
        )
        versions = [dict(r) for r in await cursor.fetchall()]
    return {
        "compiled_truth": page.get("compiled_truth") or "",
        "title": page.get("title") or "",
        "updated_at": page.get("updated_at") or "",
        "slug": slug,
        "versions": versions,
    }


@router.post("/profile/overall")
async def api_generate_overall_profile(strategy: str = Query(default="time_weighted", description="生成策略: time_weighted, recursive, dual_track")):
    """Generate overall profile with selectable strategy."""
    from app.services.compiler import generate_overall_profile
    result = await generate_overall_profile(strategy=strategy)
    return result


@router.get("/profile/overall")
async def api_get_overall_profile():
    """Get the current overall profile from pages table."""
    page = await get_page_by_slug("overall_profile")
    if page is None:
        return {"compiled_truth": "", "title": "", "updated_at": "", "versions": []}
    # Also fetch version history from page_versions
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, version_number, compiled_truth_snapshot, created_at "
            "FROM page_versions WHERE page_id = ? ORDER BY version_number DESC",
            (page["id"],),
        )
        versions = [dict(r) for r in await cursor.fetchall()]
    return {
        "compiled_truth": page.get("compiled_truth") or "",
        "title": page.get("title") or "",
        "updated_at": page.get("updated_at") or "",
        "versions": versions,
    }


@router.get("/snapshot/stats")
async def api_snapshot_stats():
    """Get snapshot statistics: token count, entity count, sections."""
    from app.services.snapshot import get_snapshot_stats
    return await get_snapshot_stats()


@router.get("/snapshot/export")
async def api_snapshot_export():
    """Export snapshot to file and return statistics."""
    from app.services.snapshot import export_snapshot
    import os
    filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "snapshots", "exported_snapshot.txt")
    return await export_snapshot(filepath)


# ---------------------------------------------------------------------------
# Memory endpoints (pre-aggregation layer)
# ---------------------------------------------------------------------------

@router.post("/memory/monthly")
async def api_generate_monthly_memory(
    year_month: str | None = Query(default=None, description="年月，格式 YYYYMM，默认为上月"),
):
    """生成月度记忆"""
    from app.services.compiler import generate_monthly_memory
    result = await generate_monthly_memory(year_month=year_month)
    return result


@router.get("/memory/monthly")
async def api_get_monthly_memory(
    year_month: str | None = Query(default=None, description="年月，格式 YYYYMM，默认为上月"),
):
    """获取月度记忆"""
    from datetime import datetime, timedelta
    if year_month is None:
        first_of_this_month = datetime.now().replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        year_month = last_month_end.strftime("%Y%m")
    slug = f"monthly_memory_{year_month}"
    page = await get_page_by_slug(slug)
    if page is None:
        return {"compiled_truth": "", "title": "", "updated_at": "", "slug": slug, "frontmatter": {}}
    return {
        "compiled_truth": page.get("compiled_truth") or "",
        "title": page.get("title") or "",
        "updated_at": page.get("updated_at") or "",
        "slug": slug,
        "frontmatter": page.get("frontmatter") or {},
    }


@router.post("/memory/yearly")
async def api_generate_yearly_memory(
    year: int | None = Query(default=None, description="年份，默认为去年"),
):
    """生成年度记忆"""
    from app.services.compiler import generate_yearly_memory
    result = await generate_yearly_memory(year=year)
    return result


@router.get("/memory/yearly")
async def api_get_yearly_memory(
    year: int | None = Query(default=None, description="年份，默认为去年"),
):
    """获取年度记忆"""
    from datetime import datetime
    if year is None:
        year = datetime.now().year - 1
    slug = f"yearly_memory_{year}"
    page = await get_page_by_slug(slug)
    if page is None:
        return {"compiled_truth": "", "title": "", "updated_at": "", "slug": slug, "frontmatter": {}}
    return {
        "compiled_truth": page.get("compiled_truth") or "",
        "title": page.get("title") or "",
        "updated_at": page.get("updated_at") or "",
        "slug": slug,
        "frontmatter": page.get("frontmatter") or {},
    }


@router.get("/lint")
async def api_lint_knowledge():
    """Run health check on knowledge base."""
    from app.services.compiler import lint_knowledge_base
    result = await lint_knowledge_base()
    return result


@router.get("/merge-suggestions")
async def api_merge_suggestions():
    """Detect merge candidate pages."""
    from app.services.compiler import detect_merge_candidates
    result = await detect_merge_candidates()
    return {"suggestions": result}