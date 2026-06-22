from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import structlog

from app.config import settings
from app.database import get_connection
from app.services.vector_store import vector_store

logger = structlog.get_logger()


async def detect_changes() -> list[dict]:
    """检测所有类型的变化，返回变化记录列表"""
    changes = []

    habit_changes = await _detect_habit_fading()
    changes.extend(habit_changes)

    trait_changes = await _detect_trait_shifts()
    changes.extend(trait_changes)

    preference_changes = await _detect_preference_changes()
    changes.extend(preference_changes)

    decision_changes = await _detect_decision_patterns()
    changes.extend(decision_changes)

    for change in changes:
        await _save_change_record(change)

    return changes


async def _detect_habit_fading() -> list[dict]:
    """习惯消退检测：某习惯类画像连续 90 天无新证据"""
    changes = []

    all_profiles = await vector_store.search_profiles(
        query_vector=[0.0] * settings.llm.embedding_dimensions,
        limit=1000,
        filter_dict={"is_active": True},
    )

    cutoff_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")

    for profile in all_profiles:
        last_updated = profile.get("last_updated", "")
        if last_updated < cutoff_date:
            changes.append({
                "type": "habit_fading",
                "description": f"习惯「{profile.get('content', '')}」可能已经消退（90天无新证据）",
                "trigger_profile_ids": json.dumps([profile["id"]]),
            })

    return changes


async def _detect_trait_shifts() -> list[dict]:
    """特质转变检测：新信号与旧画像矛盾"""
    changes = []

    inactive_profiles = await vector_store.search_profiles(
        query_vector=[0.0] * settings.llm.embedding_dimensions,
        limit=200,
        filter_dict={"is_active": False},
    )

    recent_cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    existing_ids: set[str] = set()
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT trigger_profile_ids FROM profile_changes WHERE type = 'trait_shift'"
        )
        rows = await cursor.fetchall()
        for row in rows:
            try:
                ids = json.loads(row["trigger_profile_ids"])
                existing_ids.update(ids)
            except (json.JSONDecodeError, TypeError):
                pass

    for profile in inactive_profiles:
        superseded_by = profile.get("superseded_by", "")
        if not superseded_by:
            continue
        if profile["id"] in existing_ids:
            continue

        new_profile = await vector_store.get_profile(superseded_by)
        if new_profile is None:
            continue

        new_first_seen = new_profile.get("first_seen", "")
        if new_first_seen < recent_cutoff:
            continue

        changes.append({
            "type": "trait_shift",
            "description": f"特质转变：从「{profile.get('content', '')}」变为「{new_profile.get('content', '')}」",
            "trigger_profile_ids": json.dumps([profile["id"], new_profile["id"]]),
        })

    return changes


async def _detect_preference_changes() -> list[dict]:
    """偏好变化检测：兴趣/品味维度的新旧画像对比"""
    changes = []

    profiles = await vector_store.search_profiles(
        query_vector=[0.0] * settings.llm.embedding_dimensions,
        limit=100,
        filter_dict={"is_active": True},
    )

    recent_cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    for profile in profiles:
        if profile.get("last_updated", "") <= recent_cutoff:
            continue

        metadata_str = profile.get("metadata", "")
        change_narrative = ""
        if metadata_str:
            try:
                metadata = json.loads(metadata_str)
                change_narrative = metadata.get("change_narrative", "")
            except (json.JSONDecodeError, TypeError):
                pass

        if change_narrative:
            changes.append({
                "type": "preference_change",
                "description": change_narrative,
                "trigger_profile_ids": json.dumps([profile["id"]]),
            })

    return changes


async def _detect_decision_patterns() -> list[dict]:
    """决策模式形成检测：当决策子维度画像首次生成时"""
    changes = []

    recent_cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    profiles = await vector_store.search_profiles(
        query_vector=[0.0] * settings.llm.embedding_dimensions,
        limit=10,
        filter_dict={"is_active": True},
    )

    for profile in profiles:
        if profile.get("first_seen", "") > recent_cutoff:
            changes.append({
                "type": "decision_pattern",
                "description": f"检测到新的决策模式：{profile.get('content', '')}",
                "trigger_profile_ids": json.dumps([profile["id"]]),
            })

    return changes


async def _save_change_record(change: dict) -> str:
    """保存变化记录到 profile_changes 表"""
    change_id = uuid.uuid4().hex
    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO profile_changes (id, type, description, trigger_profile_ids)
            VALUES (?, ?, ?, ?)
            """,
            (
                change_id,
                change["type"],
                change["description"],
                change.get("trigger_profile_ids", "[]"),
            ),
        )
        await db.commit()
    return change_id


async def get_unpresented_changes() -> list[dict]:
    """获取未展示的变化提醒"""
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT * FROM profile_changes
            WHERE presented = 0 AND dismissed = 0
            ORDER BY created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def mark_change_presented(change_id: str) -> None:
    """标记变化提醒为已展示"""
    async with get_connection() as db:
        await db.execute(
            "UPDATE profile_changes SET presented = 1 WHERE id = ?", (change_id,)
        )
        await db.commit()


async def dismiss_change(change_id: str) -> None:
    """用户关闭变化提醒"""
    async with get_connection() as db:
        await db.execute(
            "UPDATE profile_changes SET dismissed = 1 WHERE id = ?", (change_id,)
        )
        await db.commit()
