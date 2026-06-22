"""画像协调器 - 统一管理双画像的生成、交叉验证和存储"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta

import structlog

from app.database import get_connection
from app.services.portrait_skills.detailed_skill import generate_detailed_portrait
from app.services.portrait_skills.deep_skill import generate_deep_portrait

logger = structlog.get_logger()


async def _gather_timeline_data(days: int | None = None) -> str:
    """从数据库收集时间线事件数据

    Args:
        days: 收集最近多少天的数据，None 表示全部
    """
    conditions = []
    params: list = []

    if days is not None:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        conditions.append("timestamp >= ?")
        params.append(cutoff)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"SELECT * FROM timeline_events {where_clause} ORDER BY timestamp DESC LIMIT 500"

    async with get_connection() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

    if not rows:
        return ""

    events_text = []
    for row in rows:
        event = dict(row)
        events_text.append(
            f"[{event.get('timestamp', '')}] {event.get('event_type', '')}: {event.get('summary', '')}"
            + (f" (情绪: {event.get('sentiment', '')})" if event.get('sentiment') else "")
            + (f" [关键词: {event.get('emotional_keywords', '')}]" if event.get('emotional_keywords') else "")
            + (f" [联系人: {event.get('related_contacts', '')}]" if event.get('related_contacts') else "")
        )

    return "\n".join(events_text)


async def _gather_detailed_data() -> str:
    """收集细节画像的分层数据：L0(30天事件) + L1(12月月度记忆) + L2(年度记忆)

    降级策略：月度/年度记忆缺失时回退到读取更多原始事件。
    """
    from app.services.compiler import _read_monthly_memories, _read_yearly_memories

    sections = []

    # L0: 最近30天的 timeline_events（最多200条）
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM timeline_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 200",
            (cutoff,),
        )
        rows = await cursor.fetchall()

    if rows:
        events_text = []
        for row in rows:
            event = dict(row)
            events_text.append(
                f"[{event.get('timestamp', '')}] {event.get('event_type', '')}: {event.get('summary', '')}"
                + (f" (情绪: {event.get('sentiment', '')})" if event.get('sentiment') else "")
                + (f" [关键词: {event.get('emotional_keywords', '')}]" if event.get('emotional_keywords') else "")
            )
        sections.append(f"=== L0 原始事件（最近30天，共{len(rows)}条） ===\n" + "\n".join(events_text))
    else:
        # 降级：尝试读取90天事件
        cutoff_90 = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM timeline_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 500",
                (cutoff_90,),
            )
            rows_90 = await cursor.fetchall()
        if rows_90:
            events_text = []
            for row in rows_90:
                event = dict(row)
                events_text.append(
                    f"[{event.get('timestamp', '')}] {event.get('event_type', '')}: {event.get('summary', '')}"
                    + (f" (情绪: {event.get('sentiment', '')})" if event.get('sentiment') else "")
                )
            sections.append(f"=== L0 原始事件（降级：最近90天，共{len(rows_90)}条） ===\n" + "\n".join(events_text))

    # L1: 最近36个月的 monthly_memory
    monthly_memories = await asyncio.to_thread(_read_monthly_memories, 36)
    if monthly_memories:
        memory_texts = [f"[{mm['slug']}] {mm['compiled_truth']}" for mm in monthly_memories if mm.get("compiled_truth")]
        sections.append(f"=== L1 月度记忆（最近36个月，共{len(memory_texts)}条） ===\n" + "\n".join(memory_texts))
    else:
        sections.append("=== L1 月度记忆：暂无（降级为L0原始事件补充） ===")

    # L2: 全部 yearly_memory
    yearly_memories = await asyncio.to_thread(_read_yearly_memories)
    if yearly_memories:
        yearly_texts = [f"[{ym['slug']}] {ym['compiled_truth']}" for ym in yearly_memories if ym.get("compiled_truth")]
        sections.append(f"=== L2 年度记忆（共{len(yearly_texts)}条） ===\n" + "\n".join(yearly_texts))
    else:
        sections.append("=== L2 年度记忆：暂无 ===")

    return "\n\n".join(sections)


async def _gather_deep_data() -> str:
    """收集深度画像的分层数据：L1(36月月度记忆) + L2(年度记忆)

    不读取原始事件。降级：记忆缺失时回退到读取原始事件。
    """
    from app.services.compiler import _read_all_monthly_memories, _read_yearly_memories

    sections = []
    has_memory = False

    # L1: 最近36个月的 monthly_memory
    monthly_memories = await asyncio.to_thread(_read_all_monthly_memories)
    if monthly_memories:
        memory_texts = [f"[{mm['slug']}] {mm['compiled_truth']}" for mm in monthly_memories[:36] if mm.get("compiled_truth")]
        if memory_texts:
            has_memory = True
            sections.append(f"=== L1 月度记忆（最近36个月，共{len(memory_texts)}条） ===\n" + "\n".join(memory_texts))

    # L2: 全部 yearly_memory
    yearly_memories = await asyncio.to_thread(_read_yearly_memories)
    if yearly_memories:
        yearly_texts = [f"[{ym['slug']}] {ym['compiled_truth']}" for ym in yearly_memories if ym.get("compiled_truth")]
        if yearly_texts:
            has_memory = True
            sections.append(f"=== L2 年度记忆（共{len(yearly_texts)}条） ===\n" + "\n".join(yearly_texts))

    # 降级：如果没有记忆数据，回退到读取原始事件
    if not has_memory:
        logger.warning("deep_portrait_no_memory_fallback", message="无月度/年度记忆，降级为读取全部原始事件")
        fallback_data = await _gather_timeline_data(days=None)
        if fallback_data:
            sections.append("=== 降级：全部原始事件（无月度/年度记忆可用） ===\n" + fallback_data)

    return "\n\n".join(sections)


async def _save_portrait_to_db(portrait_type: str, modules: list[dict], extra: dict | None = None) -> str:
    """保存画像到数据库

    Args:
        portrait_type: "detailed" 或 "deep"
        modules: 画像模块列表
        extra: 额外数据（如 reflection_questions）

    Returns:
        记录 ID
    """
    record_id = uuid.uuid4().hex
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    modules_json = json.dumps(modules, ensure_ascii=False)
    extra_json = json.dumps(extra, ensure_ascii=False) if extra else None

    async with get_connection() as db:
        # 将之前的当前记录标记为非当前
        await db.execute(
            "UPDATE portrait_records SET is_current = 0 WHERE portrait_type = ? AND is_current = 1",
            (portrait_type,),
        )
        # 插入新记录
        await db.execute(
            "INSERT INTO portrait_records (id, portrait_type, modules_json, extra_json, created_at, is_current) VALUES (?, ?, ?, ?, ?, 1)",
            (record_id, portrait_type, modules_json, extra_json, now),
        )
        await db.commit()

    # 画像更新后使快照缓存失效
    from app.services.snapshot import invalidate_snapshot
    invalidate_snapshot()

    return record_id


async def run_monthly_portrait_update() -> dict:
    """执行月度画像更新

    流程：
    1. 收集分层数据（细致型取L0+L1+L2，深度型取L1+L2）
    2. 先运行细致型画像
    3. 再运行深度型画像
    4. 保存到数据库
    5. 返回合并结果
    """
    # 1. 收集数据
    detailed_data = await _gather_detailed_data()
    deep_data = await _gather_deep_data()

    # 2. 运行细致型画像
    detailed_result = await generate_detailed_portrait(detailed_data)

    # 3. 运行深度型画像
    deep_result = await generate_deep_portrait(deep_data)

    # 4. 保存到数据库
    detailed_id = await _save_portrait_to_db(
        portrait_type="detailed",
        modules=detailed_result.get("modules", []),
    )

    deep_id = await _save_portrait_to_db(
        portrait_type="deep",
        modules=deep_result.get("modules", []),
        extra={"reflection_questions": deep_result.get("reflection_questions", [])},
    )

    logger.info(
        "月度画像更新完成",
        detailed_id=detailed_id,
        deep_id=deep_id,
    )

    return {
        "detailed": {
            "id": detailed_id,
            **detailed_result,
        },
        "deep": {
            "id": deep_id,
            **deep_result,
        },
    }


async def generate_and_save_detailed() -> dict:
    """单独生成并保存细致型画像（数据源：L0+L1+L2）"""
    detailed_data = await _gather_detailed_data()
    result = await generate_detailed_portrait(detailed_data)

    record_id = await _save_portrait_to_db(
        portrait_type="detailed",
        modules=result.get("modules", []),
    )

    return {"id": record_id, **result}


async def generate_and_save_deep() -> dict:
    """单独生成并保存深度型画像（数据源：L1+L2，不读原始事件）"""
    deep_data = await _gather_deep_data()
    result = await generate_deep_portrait(deep_data)

    record_id = await _save_portrait_to_db(
        portrait_type="deep",
        modules=result.get("modules", []),
        extra={"reflection_questions": result.get("reflection_questions", [])},
    )

    return {"id": record_id, **result}


async def get_portrait_records(portrait_type: str | None = None) -> list[dict]:
    """获取画像记录

    Args:
        portrait_type: 可选，过滤 "detailed" 或 "deep"
    """
    conditions = []
    params: list = []

    if portrait_type:
        conditions.append("portrait_type = ?")
        params.append(portrait_type)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    query = f"SELECT * FROM portrait_records {where_clause} ORDER BY created_at DESC LIMIT 20"

    async with get_connection() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

    records = []
    for row in rows:
        r = dict(row)
        try:
            r["modules"] = json.loads(r.get("modules_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["modules"] = []
        try:
            r["extra"] = json.loads(r.get("extra_json", "null")) if r.get("extra_json") else None
        except (json.JSONDecodeError, TypeError):
            r["extra"] = None
        records.append(r)

    return records


async def get_portrait_versions(portrait_type: str) -> list[dict]:
    """获取指定类型的所有画像版本（不含完整 modules_json，用于版本列表展示）

    Args:
        portrait_type: "detailed" 或 "deep"

    Returns:
        版本列表，每项包含 id, portrait_type, created_at, is_current, modules_count
    """
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT id, portrait_type, created_at, is_current, modules_json FROM portrait_records WHERE portrait_type = ? ORDER BY created_at DESC",
            (portrait_type,),
        )
        rows = await cursor.fetchall()

    versions = []
    for row in rows:
        r = dict(row)
        modules_count = 0
        try:
            modules_count = len(json.loads(r.get("modules_json", "[]")))
        except (json.JSONDecodeError, TypeError):
            pass
        versions.append({
            "id": r["id"],
            "portrait_type": r["portrait_type"],
            "created_at": r["created_at"],
            "is_current": r["is_current"],
            "modules_count": modules_count,
        })

    return versions


async def get_portrait_version_by_id(version_id: str) -> dict | None:
    """获取指定 ID 的画像版本（含完整数据）

    Args:
        version_id: 画像记录 ID

    Returns:
        完整画像记录，包含 modules 和 extra
    """
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM portrait_records WHERE id = ?",
            (version_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    r = dict(row)
    try:
        r["modules"] = json.loads(r.get("modules_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        r["modules"] = []
    try:
        r["extra"] = json.loads(r.get("extra_json", "null")) if r.get("extra_json") else None
    except (json.JSONDecodeError, TypeError):
        r["extra"] = None

    return r


async def get_current_portrait(portrait_type: str) -> dict | None:
    """获取当前生效的画像

    Args:
        portrait_type: "detailed" 或 "deep"
    """
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM portrait_records WHERE portrait_type = ? AND is_current = 1 ORDER BY created_at DESC LIMIT 1",
            (portrait_type,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    r = dict(row)
    try:
        r["modules"] = json.loads(r.get("modules_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        r["modules"] = []
    try:
        r["extra"] = json.loads(r.get("extra_json", "null")) if r.get("extra_json") else None
    except (json.JSONDecodeError, TypeError):
        r["extra"] = None

    return r
