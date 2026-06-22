from __future__ import annotations

from app.database import get_connection


async def lint_brain() -> dict:
    orphan_pages: list[str] = []
    stale_pages: list[str] = []
    inconsistencies: list[str] = []
    suggestions: list[str] = []

    async with get_connection() as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM pages")
        row = await cursor.fetchone()
        total_pages = row[0] if row else 0

        cursor = await db.execute(
            "SELECT p.slug FROM pages p LEFT JOIN links l ON p.id = l.target_page_id "
            "WHERE l.target_page_id IS NULL AND p.type != 'system'"
        )
        rows = await cursor.fetchall()
        orphan_pages = [r[0] for r in rows]

        cursor = await db.execute(
            "SELECT slug FROM pages WHERE updated_at < datetime('now', '-30 days') AND type != 'system'"
        )
        rows = await cursor.fetchall()
        stale_pages = [r[0] for r in rows]

        cursor = await db.execute(
            "SELECT tag, COUNT(DISTINCT page_id) as usage_count FROM tags GROUP BY tag HAVING usage_count = 1"
        )
        rows = await cursor.fetchall()
        for r in rows:
            inconsistencies.append(f"标签 '{r[0]}' 仅使用了一次")

        if orphan_pages:
            suggestions.append(
                f"发现 {len(orphan_pages)} 个孤立页面，建议添加链接或合并到相关页面"
            )

        if stale_pages:
            suggestions.append(
                f"发现 {len(stale_pages)} 个超过 30 天未更新的页面，建议检查是否需要更新"
            )

        if inconsistencies:
            suggestions.append(
                f"发现 {len(inconsistencies)} 个标签不一致，建议清理或合并标签"
            )

    return {
        "total_pages": total_pages,
        "orphan_pages": orphan_pages,
        "stale_pages": stale_pages,
        "inconsistencies": inconsistencies,
        "suggestions": suggestions,
    }