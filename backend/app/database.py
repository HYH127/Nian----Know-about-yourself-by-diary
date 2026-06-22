from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
import sqlite3

from app.config import settings

_db: aiosqlite.Connection | None = None
_compile_sync_db: sqlite3.Connection | None = None

_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-64000",
    "PRAGMA foreign_keys=ON",
]

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mode TEXT DEFAULT 'chat',
    session_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS diaries (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    content TEXT NOT NULL,
    extracted_summary TEXT,
    extracted_tags TEXT,
    chat_message_id TEXT,
    location TEXT,
    weather TEXT,
    temperature TEXT,
    humidity TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (chat_message_id) REFERENCES messages(id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS diaries_fts USING fts5(
    id, date, content, extracted_summary, extracted_tags, location,
    content='diaries', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS wechat_message_stats (
    id TEXT PRIMARY KEY,
    contact_name TEXT NOT NULL,
    sender TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    word_count INTEGER,
    has_emoji BOOLEAN DEFAULT FALSE,
    has_image BOOLEAN DEFAULT FALSE,
    has_voice BOOLEAN DEFAULT FALSE,
    sentiment_score REAL,
    topic_category TEXT,
    message_hash TEXT NOT NULL,
    response_delay_seconds INTEGER,
    import_batch_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_wcs_contact ON wechat_message_stats(contact_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_wcs_batch ON wechat_message_stats(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_wcs_hash ON wechat_message_stats(message_hash);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    sentiment REAL,
    emotional_keywords TEXT,
    related_contacts TEXT,
    related_events TEXT,
    related_page_slugs TEXT,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    importance_score REAL DEFAULT 0.5,
    is_milestone INTEGER DEFAULT 0,
    is_confirmed INTEGER DEFAULT 0,
    confirmed_at TEXT,
    is_locked INTEGER DEFAULT 0,
    locked_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_timeline_timestamp ON timeline_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_timeline_type_time ON timeline_events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_timeline_contact_time ON timeline_events(related_contacts, timestamp);
CREATE INDEX IF NOT EXISTS idx_timeline_sentiment ON timeline_events(sentiment);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    user_status TEXT DEFAULT 'mentioned',
    user_consumed_date TEXT,
    user_rating REAL,
    user_notes TEXT,
    summary TEXT,
    genres TEXT,
    key_characters TEXT,
    themes TEXT,
    creator TEXT,
    year INTEGER,
    source_url TEXT,
    plot_detail TEXT,
    cultural_impact TEXT,
    reviews_summary TEXT,
    similar_works TEXT,
    depth_level INTEGER DEFAULT 1,
    search_performed_at TEXT,
    last_updated_at TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title, summary, genres, themes, creator,
    content='knowledge_base',
    content_rowid='rowid'
);
CREATE INDEX IF NOT EXISTS idx_kb_type ON knowledge_base(type);
CREATE INDEX IF NOT EXISTS idx_kb_title ON knowledge_base(title);
CREATE INDEX IF NOT EXISTS idx_kb_depth ON knowledge_base(depth_level);

CREATE TABLE IF NOT EXISTS profile_changes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    trigger_profile_ids TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    presented INTEGER DEFAULT 0,
    dismissed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wechat_tier2_messages (
    id TEXT PRIMARY KEY,
    message_hash TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    sender TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    encrypted_content TEXT NOT NULL,
    import_batch_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_t2_contact ON wechat_tier2_messages(contact_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_t2_batch ON wechat_tier2_messages(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_t2_hash ON wechat_tier2_messages(message_hash);

CREATE TABLE IF NOT EXISTS wechat_tier3_messages (
    id TEXT PRIMARY KEY,
    message_hash TEXT NOT NULL,
    contact_name TEXT NOT NULL,
    sender TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    encrypted_content TEXT NOT NULL,
    import_batch_id TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_t3_contact ON wechat_tier3_messages(contact_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_t3_batch ON wechat_tier3_messages(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_t3_hash ON wechat_tier3_messages(message_hash);
CREATE INDEX IF NOT EXISTS idx_t3_expires ON wechat_tier3_messages(expires_at);

CREATE TABLE IF NOT EXISTS wechat_privacy_tiers (
    contact_name TEXT PRIMARY KEY,
    privacy_tier TEXT NOT NULL DEFAULT 'tier1',
    tier2_authorized INTEGER DEFAULT 0,
    tier3_authorized INTEGER DEFAULT 0,
    tier3_expires_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media_records (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    media_type TEXT NOT NULL,
    consumed_date TEXT,
    rating REAL,
    notes TEXT,
    source_type TEXT NOT NULL DEFAULT 'media',
    source_id TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_mr_type ON media_records(media_type);
CREATE INDEX IF NOT EXISTS idx_mr_date ON media_records(consumed_date);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL DEFAULT 'concept',
    title TEXT NOT NULL,
    frontmatter TEXT DEFAULT '{}',
    aliases TEXT DEFAULT '[]',
    compiled_truth TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    timeline TEXT DEFAULT '[]',
    merged_from TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    slug, title, compiled_truth,
    content='pages', content_rowid='rowid'
);

CREATE TABLE IF NOT EXISTS content_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding BLOB,
    chunk_index INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    target_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    link_type TEXT DEFAULT 'reference',
    confidence TEXT DEFAULT 'reference'
);

CREATE TABLE IF NOT EXISTS tags (
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (page_id, tag)
);

CREATE TABLE IF NOT EXISTS page_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    compiled_truth_snapshot TEXT DEFAULT '',
    timeline_snapshot TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS raw_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_json TEXT NOT NULL,
    entity_tags TEXT DEFAULT '[]',
    status TEXT DEFAULT 'unprocessed',
    source_type TEXT DEFAULT '',
    source_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ingest_log (
    file_path TEXT PRIMARY KEY,
    sha256 TEXT,
    status TEXT DEFAULT 'imported',
    timestamp TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_pages_type ON pages(type);
CREATE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug);
CREATE INDEX IF NOT EXISTS idx_chunks_page ON content_chunks(page_id);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_page_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_page_id);
CREATE INDEX IF NOT EXISTS idx_signals_status ON raw_signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_entity ON raw_signals(entity_tags);
CREATE INDEX IF NOT EXISTS idx_versions_page ON page_versions(page_id);

CREATE TABLE IF NOT EXISTS portrait_records (
    id TEXT PRIMARY KEY,
    portrait_type TEXT NOT NULL,
    modules_json TEXT NOT NULL DEFAULT '[]',
    extra_json TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    is_current INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_portrait_type ON portrait_records(portrait_type);
CREATE INDEX IF NOT EXISTS idx_portrait_current ON portrait_records(portrait_type, is_current);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    entity_tag TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    description TEXT NOT NULL,
    old_statement TEXT,
    new_statement TEXT,
    status TEXT DEFAULT 'pending',
    resolution TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status);

CREATE TABLE IF NOT EXISTS quick_notes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    edited_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    processing_status TEXT DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_qn_edited ON quick_notes(edited_at);

CREATE TABLE IF NOT EXISTS expense_records (
    id TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    note TEXT,
    expense_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_er_date ON expense_records(expense_date);
CREATE INDEX IF NOT EXISTS idx_er_category ON expense_records(category);

CREATE TABLE IF NOT EXISTS user_feedback (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_slug TEXT NOT NULL,
    error_type TEXT NOT NULL,
    correction_text TEXT,
    context_snapshot TEXT,
    is_active INTEGER DEFAULT 1,
    valid_until TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_active ON user_feedback(is_active, target_type);
CREATE INDEX IF NOT EXISTS idx_feedback_valid ON user_feedback(valid_until);
"""


async def init_db() -> None:
    global _db, _compile_sync_db

    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(str(db_path))
    _db.row_factory = aiosqlite.Row

    for pragma in _PRAGMAS:
        await _db.execute(pragma)

    await _db.executescript(_CREATE_TABLES_SQL)
    await _db.commit()

    # Migration: add confidence column to links if missing
    try:
        await _db.execute("ALTER TABLE links ADD COLUMN confidence TEXT DEFAULT 'reference'")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    try:
        await _db.execute("ALTER TABLE pages ADD COLUMN summary TEXT DEFAULT ''")
        await _db.commit()
    except Exception:
        pass

    try:
        await _db.execute("ALTER TABLE pages ADD COLUMN aliases TEXT DEFAULT '[]'")
        await _db.commit()
    except Exception:
        pass

    # Migration: add related_page_slugs column to timeline_events
    try:
        await _db.execute("ALTER TABLE timeline_events ADD COLUMN related_page_slugs TEXT")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    # Migration: add index for related_page_slugs
    try:
        await _db.execute("CREATE INDEX IF NOT EXISTS idx_timeline_page_slugs ON timeline_events(related_page_slugs)")
        await _db.commit()
    except Exception:
        pass

    # Migration: create portrait_records table if not exists (for older databases)
    try:
        await _db.execute("""
            CREATE TABLE IF NOT EXISTS portrait_records (
                id TEXT PRIMARY KEY,
                portrait_type TEXT NOT NULL,
                modules_json TEXT NOT NULL DEFAULT '[]',
                extra_json TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                is_current INTEGER DEFAULT 1
            )
        """)
        await _db.execute("CREATE INDEX IF NOT EXISTS idx_portrait_type ON portrait_records(portrait_type)")
        await _db.execute("CREATE INDEX IF NOT EXISTS idx_portrait_current ON portrait_records(portrait_type, is_current)")
        await _db.commit()
    except Exception:
        pass

    # Migration: add is_confirmed and confirmed_at columns to timeline_events
    try:
        await _db.execute("ALTER TABLE timeline_events ADD COLUMN is_confirmed INTEGER DEFAULT 0")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    try:
        await _db.execute("ALTER TABLE timeline_events ADD COLUMN confirmed_at TEXT")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    try:
        await _db.execute("CREATE INDEX IF NOT EXISTS idx_timeline_confirmed ON timeline_events(is_confirmed)")
        await _db.commit()
    except Exception:
        pass

    # Migration: add content column to timeline_events (original evidence sentence)
    try:
        await _db.execute("ALTER TABLE timeline_events ADD COLUMN content TEXT DEFAULT ''")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    # Migration: add is_locked and locked_at columns to timeline_events
    try:
        await _db.execute("ALTER TABLE timeline_events ADD COLUMN is_locked INTEGER DEFAULT 0")
        await _db.commit()
    except Exception:
        pass

    try:
        await _db.execute("ALTER TABLE timeline_events ADD COLUMN locked_at TEXT")
        await _db.commit()
    except Exception:
        pass

    # Migration: add merged_from column to pages
    try:
        await _db.execute("ALTER TABLE pages ADD COLUMN merged_from TEXT")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    # Migration: add last_compiled_at column to pages (时间线驱动编译用)
    try:
        await _db.execute("ALTER TABLE pages ADD COLUMN last_compiled_at TEXT")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    # Migration: add processing_status column to diaries
    try:
        await _db.execute("ALTER TABLE diaries ADD COLUMN processing_status TEXT DEFAULT 'pending'")
        await _db.commit()
    except Exception:
        pass  # Column already exists

    # Migration: add location/weather/temperature/humidity columns to diaries
    for col, col_type in [
        ("location", "TEXT"),
        ("weather", "TEXT"),
        ("temperature", "TEXT"),
        ("humidity", "TEXT"),
    ]:
        try:
            await _db.execute(f"ALTER TABLE diaries ADD COLUMN {col} {col_type}")
            await _db.commit()
        except Exception:
            pass  # Column already exists

    try:
        await _db.execute("CREATE INDEX IF NOT EXISTS idx_diaries_status ON diaries(processing_status)")
        await _db.commit()
    except Exception:
        pass

    # Migration: create merge_snapshots table for undo support
    try:
        await _db.execute("""
            CREATE TABLE IF NOT EXISTS merge_snapshots (
                id TEXT PRIMARY KEY,
                target_slug TEXT NOT NULL,
                source_slugs TEXT NOT NULL,
                snapshot_data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        await _db.commit()
    except Exception:
        pass

    # Create a separate synchronous connection for the compile scheduler
    # This avoids aiosqlite event loop issues that can block the main event loop
    _compile_sync_db = sqlite3.connect(str(db_path), check_same_thread=False)
    _compile_sync_db.row_factory = sqlite3.Row
    for pragma in _PRAGMAS:
        _compile_sync_db.execute(pragma)

    # Verify compile connection works
    try:
        cursor = _compile_sync_db.execute("SELECT COUNT(*) as cnt FROM pages")
        row = cursor.fetchone()
        print(f"[init_db] compile_sync_db verified: {row['cnt']} pages")
    except Exception as e:
        print(f"[init_db] compile_sync_db verification FAILED: {e}")


async def close_db() -> None:
    global _db, _compile_sync_db
    if _compile_sync_db:
        _compile_sync_db.close()
        _compile_sync_db = None
    if _db:
        await _db.close()
        _db = None


@asynccontextmanager
async def get_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    if _db is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    yield _db


def get_compile_sync_connection() -> sqlite3.Connection:
    """Get the synchronous database connection for the compile scheduler.
    This runs in a separate thread via asyncio.to_thread, so it doesn't block the event loop."""
    if _compile_sync_db is None:
        raise RuntimeError("编译数据库未初始化，请先调用 init_db()")
    return _compile_sync_db
