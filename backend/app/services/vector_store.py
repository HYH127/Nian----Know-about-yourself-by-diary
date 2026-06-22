from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import lancedb
import pyarrow as pa

from app.config import settings
from app.models.profile import ProfileFragment

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_VECTORS_DIR = _BASE_DIR / "data" / "vectors"

_EMBEDDING_DIM = settings.llm.embedding_dimensions

PROFILES_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("content", pa.string()),
    pa.field("confidence", pa.string()),
    pa.field("evidence", pa.list_(pa.string())),
    pa.field("frequency", pa.int32()),
    pa.field("first_seen", pa.string()),
    pa.field("last_updated", pa.string()),
    pa.field("is_active", pa.bool_()),
    pa.field("superseded_by", pa.string()),
    pa.field("trigger", pa.string()),
    pa.field("behavior", pa.string()),
    pa.field("context", pa.string()),
    pa.field("related_entity", pa.string()),
    pa.field("relation_type", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
    pa.field("source", pa.string()),
    pa.field("metadata", pa.string()),
])

KNOWLEDGE_SCHEMA = pa.schema([
    pa.field("kb_id", pa.string()),
    pa.field("title", pa.string()),
    pa.field("type", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("genres", pa.string()),
    pa.field("themes", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
])

DIARIES_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("source_type", pa.string()),
    pa.field("source_id", pa.string()),
    pa.field("chunk_index", pa.int32()),
    pa.field("source_date", pa.string()),
    pa.field("content", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
])

TIMELINE_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("timestamp", pa.string()),
    pa.field("event_type", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("content", pa.string()),
    pa.field("source_type", pa.string()),
    pa.field("source_id", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
])

ENTITIES_SCHEMA = pa.schema([
    pa.field("slug", pa.string()),
    pa.field("title", pa.string()),
    pa.field("type", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("compiled_truth_preview", pa.string()),  # compiled_truth 前 300 字，用于展示
    pa.field("aliases", pa.string()),                  # JSON 数组字符串，用于名称匹配
    pa.field("updated_at", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), _EMBEDDING_DIM)),
])

_db: lancedb.DBConnection | None = None


def _get_db() -> lancedb.DBConnection:
    global _db
    if _db is None:
        _VECTORS_DIR.mkdir(parents=True, exist_ok=True)
        _db = lancedb.connect(str(_VECTORS_DIR))
    return _db


def _ensure_table(db: lancedb.DBConnection, name: str, schema: pa.Schema) -> lancedb.table.Table:
    try:
        return db.open_table(name)
    except ValueError:
        db.create_table(name, schema=schema)
        return db.open_table(name)


def _fragment_to_row(fragment: ProfileFragment, vector: list[float]) -> dict:
    return {
        "id": fragment.id,
        "content": fragment.content,
        "confidence": fragment.confidence,
        "evidence": fragment.evidence,
        "frequency": fragment.frequency,
        "first_seen": fragment.first_seen,
        "last_updated": fragment.last_updated,
        "is_active": fragment.is_active,
        "superseded_by": fragment.superseded_by or "",
        "trigger": fragment.trigger or "",
        "behavior": fragment.behavior or "",
        "context": fragment.context or "",
        "related_entity": fragment.related_entity or "",
        "relation_type": fragment.relation_type or "",
        "vector": vector,
        "source": fragment.source or "",
        "metadata": fragment.metadata or "",
    }


def _build_filter(filter_dict: dict | None) -> str | None:
    if not filter_dict:
        return None
    parts = []
    for key, value in filter_dict.items():
        if isinstance(value, bool):
            parts.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, (int, float)):
            parts.append(f"{key} = {value}")
        else:
            parts.append(f"{key} = '{value}'")
    return " AND ".join(parts)


class VectorStore:
    _instance: Optional["VectorStore"] = None

    def __new__(cls) -> "VectorStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

    async def _get_profiles_table(self) -> lancedb.table.Table:
        db = await asyncio.to_thread(_get_db)
        return await asyncio.to_thread(_ensure_table, db, "profiles", PROFILES_SCHEMA)

    async def _get_knowledge_table(self) -> lancedb.table.Table:
        db = await asyncio.to_thread(_get_db)
        return await asyncio.to_thread(_ensure_table, db, "knowledge", KNOWLEDGE_SCHEMA)

    async def add_profile(self, fragment: ProfileFragment, vector: list[float]) -> None:
        table = await self._get_profiles_table()
        row = _fragment_to_row(fragment, vector)
        await asyncio.to_thread(table.add, [row])

    async def search_profiles(
        self,
        query_vector: list[float],
        limit: int = 10,
        filter_dict: dict | None = None,
    ) -> list[dict]:
        table = await self._get_profiles_table()
        query = table.search(query_vector).limit(limit)
        filter_str = _build_filter(filter_dict)
        if filter_str:
            query = query.where(filter_str)
        results = await asyncio.to_thread(query.to_pandas)
        if results.empty:
            return []
        return results.to_dict(orient="records")

    async def get_profile(self, profile_id: str) -> dict | None:
        table = await self._get_profiles_table()
        results = await asyncio.to_thread(
            lambda: table.search().where(f"id = '{profile_id}'").limit(1).to_pandas()
        )
        if results.empty:
            return None
        return results.iloc[0].to_dict()

    async def update_profile(self, profile_id: str, updates: dict) -> None:
        table = await self._get_profiles_table()
        existing = await self.get_profile(profile_id)
        if existing is None:
            return
        if "vector" not in updates:
            updates["vector"] = existing.get("vector", [])
        await asyncio.to_thread(table.delete, f"id = '{profile_id}'")
        merged = {**existing, **updates}
        await asyncio.to_thread(table.add, [merged])

    async def deactivate_profile(self, profile_id: str, superseded_by: str) -> None:
        await self.update_profile(profile_id, {
            "is_active": False,
            "superseded_by": superseded_by,
        })

    async def delete_profile(self, profile_id: str) -> None:
        table = await self._get_profiles_table()
        await asyncio.to_thread(table.delete, f"id = '{profile_id}'")

    async def clear_all(self) -> None:
        """清空 profiles 表所有数据（删除并重建表以释放磁盘空间）"""
        db = await asyncio.to_thread(_get_db)
        try:
            await asyncio.to_thread(db.drop_table, "profiles")
        except Exception:
            pass

    async def clear_knowledge(self) -> None:
        """清空 knowledge 表所有数据（删除并重建表以释放磁盘空间）"""
        db = await asyncio.to_thread(_get_db)
        try:
            await asyncio.to_thread(db.drop_table, "knowledge")
        except Exception:
            pass

    async def add_knowledge(
        self,
        kb_id: str,
        title: str,
        type: str,
        summary: str,
        genres: str,
        themes: str,
        vector: list[float],
    ) -> None:
        table = await self._get_knowledge_table()
        row = {
            "kb_id": kb_id,
            "title": title,
            "type": type,
            "summary": summary,
            "genres": genres,
            "themes": themes,
            "vector": vector,
        }
        await asyncio.to_thread(table.add, [row])

    async def search_knowledge(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[dict]:
        table = await self._get_knowledge_table()
        results = await asyncio.to_thread(
            lambda: table.search(query_vector).limit(limit).to_pandas()
        )
        if results.empty:
            return []
        return results.to_dict(orient="records")

    async def _get_diaries_table(self) -> lancedb.table.Table:
        db = await asyncio.to_thread(_get_db)
        return await asyncio.to_thread(_ensure_table, db, "diaries", DIARIES_SCHEMA)

    async def add_diary_chunk(
        self,
        chunk_id: str,
        source_type: str,
        source_id: str,
        chunk_index: int,
        source_date: str,
        content: str,
        vector: list[float],
    ) -> None:
        table = await self._get_diaries_table()
        row = {
            "id": chunk_id,
            "source_type": source_type,
            "source_id": source_id,
            "chunk_index": chunk_index,
            "source_date": source_date,
            "content": content,
            "vector": vector,
        }
        await asyncio.to_thread(table.add, [row])

    async def search_diaries(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[dict]:
        table = await self._get_diaries_table()
        results = await asyncio.to_thread(
            lambda: table.search(query_vector).limit(limit).to_pandas()
        )
        if results.empty:
            return []
        return results.to_dict(orient="records")

    async def delete_diary_chunks(self, source_id: str) -> None:
        table = await self._get_diaries_table()
        await asyncio.to_thread(table.delete, f"source_id = '{source_id}'")

    async def _get_timeline_table(self) -> lancedb.table.Table:
        db = await asyncio.to_thread(_get_db)
        return await asyncio.to_thread(_ensure_table, db, "timeline", TIMELINE_SCHEMA)

    async def add_timeline_event(
        self,
        event_id: str,
        timestamp: str,
        event_type: str,
        summary: str,
        content: str,
        source_type: str,
        source_id: str,
        vector: list[float],
    ) -> None:
        table = await self._get_timeline_table()
        row = {
            "id": event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "summary": summary,
            "content": content,
            "source_type": source_type,
            "source_id": source_id,
            "vector": vector,
        }
        await asyncio.to_thread(table.add, [row])

    async def search_timeline(
        self,
        query_vector: list[float],
        limit: int = 5,
    ) -> list[dict]:
        """向量检索时间线事件。返回结果按相似度倒序，包含 _distance 字段（越小越相似）。"""
        table = await self._get_timeline_table()
        results = await asyncio.to_thread(
            lambda: table.search(query_vector).limit(limit).to_pandas()
        )
        if results.empty:
            return []
        return results.to_dict(orient="records")

    async def update_timeline_event(
        self,
        event_id: str,
        timestamp: str,
        event_type: str,
        summary: str,
        content: str,
        source_type: str,
        source_id: str,
        vector: list[float],
    ) -> None:
        """更新时间线向量：先删后加（LanceDB 不支持原地更新）"""
        table = await self._get_timeline_table()
        await asyncio.to_thread(table.delete, f"id = '{event_id}'")
        row = {
            "id": event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "summary": summary,
            "content": content,
            "source_type": source_type,
            "source_id": source_id,
            "vector": vector,
        }
        await asyncio.to_thread(table.add, [row])

    async def delete_timeline_event(self, event_id: str) -> None:
        table = await self._get_timeline_table()
        await asyncio.to_thread(table.delete, f"id = '{event_id}'")

    async def _get_entities_table(self) -> lancedb.table.Table:
        db = await asyncio.to_thread(_get_db)
        return await asyncio.to_thread(_ensure_table, db, "entities", ENTITIES_SCHEMA)

    async def upsert_entity(
        self,
        slug: str,
        title: str,
        entity_type: str,
        summary: str,
        compiled_truth_preview: str,
        aliases: str,
        updated_at: str,
        vector: list[float],
    ) -> None:
        """写入或更新实体向量（先删后加）"""
        table = await self._get_entities_table()
        await asyncio.to_thread(table.delete, f"slug = '{slug}'")
        row = {
            "slug": slug,
            "title": title,
            "type": entity_type,
            "summary": summary,
            "compiled_truth_preview": compiled_truth_preview,
            "aliases": aliases,
            "updated_at": updated_at,
            "vector": vector,
        }
        await asyncio.to_thread(table.add, [row])

    async def delete_entity(self, slug: str) -> None:
        table = await self._get_entities_table()
        await asyncio.to_thread(table.delete, f"slug = '{slug}'")

    async def search_entities(
        self,
        query_vector: list[float],
        limit: int = 20,
    ) -> list[dict]:
        """向量检索实体。返回结果按相似度倒序，包含 _distance 字段。"""
        table = await self._get_entities_table()
        results = await asyncio.to_thread(
            lambda: table.search(query_vector).limit(limit).to_pandas()
        )
        if results.empty:
            return []
        return results.to_dict(orient="records")

    async def load_all_entities(self) -> list[dict]:
        """加载所有实体（用于名称匹配）。比 SQLite 全量查询快（向量库内存缓存）。"""
        table = await self._get_entities_table()
        results = await asyncio.to_thread(lambda: table.to_pandas())
        if results.empty:
            return []
        return results.to_dict(orient="records")


vector_store = VectorStore()
