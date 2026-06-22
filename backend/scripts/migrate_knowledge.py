import asyncio
import json
import sys
from pathlib import Path

import aiosqlite

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "data" / "diary_agent.db"


async def migrate(drop_old: bool = False) -> None:
    from app.database import init_db

    await init_db()

    from app.database import get_connection

    async with get_connection() as db:

        rows = await db.execute_fetchall("SELECT * FROM knowledge_base")
        print(f"Found {len(rows)} rows in knowledge_base")

        count = 0
        for row in rows:
            title = row["title"] or ""
            slug = f"media-{title}"

            frontmatter = {
                "creator": row["creator"] or "",
                "year": row["year"],
                "genres": row["genres"] or "",
                "key_characters": row["key_characters"] or "",
                "themes": row["themes"] or "",
                "cultural_impact": row["cultural_impact"] or "",
                "reviews_summary": row["reviews_summary"] or "",
                "similar_works": row["similar_works"] or "",
                "source_url": row["source_url"] or "",
            }

            compiled_truth = row["summary"] or ""

            try:
                await db.execute(
                    """INSERT INTO pages (slug, type, title, frontmatter, compiled_truth)
                       VALUES (?, 'media', ?, ?, ?)""",
                    (
                        slug,
                        title,
                        json.dumps(frontmatter, ensure_ascii=False),
                        compiled_truth,
                    ),
                )
                count += 1
            except Exception as e:
                print(f"  Skipping '{title}': {e}")

        await db.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        await db.commit()
        print(f"Migrated {count} rows to pages table")
        print("FTS5 index rebuilt for pages_fts")

        if drop_old:
            print("Dropping old knowledge_base and knowledge_fts tables...")
            await db.execute("DROP TABLE IF EXISTS knowledge_fts")
            await db.execute("DROP TABLE IF EXISTS knowledge_base")
            await db.commit()
            print("Old tables dropped")
        else:
            print("Old tables preserved (use --drop-old to drop them)")


def main():
    drop_old = "--drop-old" in sys.argv
    asyncio.run(migrate(drop_old=drop_old))


if __name__ == "__main__":
    main()