from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from app.database import get_connection
from app.models.profile import ProfileFragment
from app.services.profile_builder import list_profiles, get_profile_by_id, get_character_summary
from app.services.profile_manager import profile_manager
from app.services.vector_store import vector_store

from app.services.change_detector import get_unpresented_changes, mark_change_presented, dismiss_change
from app.services.portrait_skills.coordinator import (
    generate_and_save_detailed,
    generate_and_save_deep,
    get_portrait_records,
    get_current_portrait,
    get_portrait_versions,
    get_portrait_version_by_id,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=list[ProfileFragment])
async def api_list_profiles():
    return await list_profiles()


@router.get("/export")
async def export_profiles():
    """导出全部画像数据为 JSON"""
    profiles = await list_profiles()
    return {"profiles": profiles, "exported_at": datetime.now().isoformat()}


@router.delete("/all")
async def delete_all_profiles():
    """一键删除所有画像数据（SQLite + LanceDB）"""
    # 先通过LanceDB API删除表（释放磁盘空间）
    await vector_store.clear_all()
    await vector_store.clear_knowledge()

    async with get_connection() as db:
        await db.execute("DELETE FROM profile_changes")
        await db.execute("DELETE FROM timeline_events")
        await db.execute("DELETE FROM diaries")
        await db.execute("DELETE FROM diaries_fts")
        await db.execute("DELETE FROM messages")
        await db.execute("DELETE FROM wechat_message_stats")
        await db.execute("DELETE FROM wechat_tier2_messages")
        await db.execute("DELETE FROM wechat_tier3_messages")
        await db.execute("DELETE FROM wechat_privacy_tiers")
        await db.execute("DELETE FROM knowledge_base")
        await db.execute("DELETE FROM knowledge_fts")
        await db.execute("DELETE FROM pages")
        await db.execute("DELETE FROM pages_fts")
        await db.execute("DELETE FROM content_chunks")
        await db.execute("DELETE FROM links")
        await db.execute("DELETE FROM tags")
        await db.execute("DELETE FROM page_versions")
        await db.execute("DELETE FROM raw_signals")
        await db.execute("DELETE FROM ingest_log")
        await db.execute("DELETE FROM media_records")
        await db.execute("DELETE FROM portrait_records")
        await db.execute("DELETE FROM quick_notes")
        await db.execute("DELETE FROM expense_records")
        await db.commit()

    import os, glob
    memory_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data", "memory")
    if os.path.exists(memory_dir):
        for f in glob.glob(os.path.join(memory_dir, "*.json")):
            os.remove(f)

    return {"status": "ok", "message": "所有数据已删除"}


@router.get("/distill")
async def distill_personality(
    contact_name: str = Query(..., description="联系人名称"),
    relationship_type: str = Query(default="", description="关系类型"),
):
    """人格蒸馏：从画像片段中提取关系特定人格面"""
    result = await profile_manager.distill_personality(
        contact_name=contact_name,
        relationship_type=relationship_type,
    )
    return result


@router.get("/changes")
async def get_profile_changes():
    """获取画像变化记录"""
    changes = await get_unpresented_changes()
    return changes


@router.put("/changes/{change_id}/acknowledge")
async def acknowledge_change(change_id: str):
    """确认变化提醒"""
    await mark_change_presented(change_id)
    return {"status": "ok"}


@router.put("/changes/{change_id}/dismiss")
async def dismiss_change_route(change_id: str):
    """关闭变化提醒"""
    await dismiss_change(change_id)
    return {"status": "ok"}


@router.get("/conflicts")
async def api_get_conflicts(
    status: Optional[str] = Query(default=None, description="过滤状态: pending | auto_resolved | user_confirmed | dismissed"),
):
    """获取冲突队列列表"""
    async with get_connection() as db:
        if status:
            rows = await db.execute_fetchall(
                "SELECT * FROM conflicts WHERE status = ? ORDER BY created_at DESC LIMIT 50",
                [status],
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT * FROM conflicts ORDER BY created_at DESC LIMIT 50",
            )
    return [dict(row) for row in rows]


@router.post("/conflicts/{conflict_id}/resolve")
async def api_resolve_conflict(conflict_id: str):
    """解决冲突（用户确认）"""
    async with get_connection() as db:
        cursor = await db.execute(
            "UPDATE conflicts SET status = 'user_confirmed', resolution = ?, resolved_at = datetime('now', 'localtime') WHERE id = ?",
            ["用户确认解决", conflict_id],
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="冲突记录不存在")
    return {"status": "ok"}


@router.post("/conflicts/{conflict_id}/dismiss")
async def api_dismiss_conflict(conflict_id: str):
    """忽略冲突"""
    async with get_connection() as db:
        cursor = await db.execute(
            "UPDATE conflicts SET status = 'dismissed', resolution = '用户忽略', resolved_at = datetime('now', 'localtime') WHERE id = ?",
            [conflict_id],
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="冲突记录不存在")
    return {"status": "ok"}


class FeedbackSubmitRequest(BaseModel):
    target_type: str
    target_slug: str
    error_type: str
    correction_text: Optional[str] = None


@router.post("/feedback")
async def api_submit_feedback(body: FeedbackSubmitRequest):
    """提交用户反馈"""
    from app.services.feedback_service import submit_feedback
    feedback_id = await submit_feedback(
        target_type=body.target_type,
        target_slug=body.target_slug,
        error_type=body.error_type,
        correction_text=body.correction_text,
    )
    return {"status": "ok", "id": feedback_id}


@router.get("/feedback")
async def api_list_feedback(
    target_type: Optional[str] = Query(default=None),
    is_active: Optional[int] = Query(default=None),
):
    """获取反馈列表"""
    async with get_connection() as db:
        query = "SELECT * FROM user_feedback WHERE 1=1"
        params: list = []
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type)
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(is_active)
        query += " ORDER BY created_at DESC LIMIT 50"
        rows = await db.execute_fetchall(query, params)
    return [dict(row) for row in rows]


@router.post("/feedback/{feedback_id}/reactivate")
async def api_reactivate_feedback(feedback_id: str):
    """复活过期反馈"""
    from app.services.feedback_service import reactivate_feedback
    await reactivate_feedback(feedback_id)
    return {"status": "ok"}


@router.delete("/feedback/{feedback_id}")
async def api_delete_feedback(feedback_id: str):
    """删除反馈"""
    from app.services.feedback_service import delete_feedback
    await delete_feedback(feedback_id)
    return {"status": "ok"}


@router.get("/character/summary")
async def api_get_character_summary():
    """获取人物特质总结和人物面貌描述"""
    result = await get_character_summary()
    return result


@router.post("/generate/detailed")
async def api_generate_detailed_portrait():
    """触发细致型画像生成"""
    result = await generate_and_save_detailed()
    return result


@router.post("/generate/deep")
async def api_generate_deep_portrait():
    """触发深度型画像生成"""
    result = await generate_and_save_deep()
    return result


@router.get("/records")
async def api_get_portrait_records(
    type: Optional[str] = Query(default=None, description="画像类型: detailed 或 deep"),
):
    """获取画像记录列表"""
    records = await get_portrait_records(portrait_type=type)
    return records


@router.get("/versions")
async def api_get_portrait_versions(
    type: str = Query(..., description="画像类型: detailed 或 deep"),
):
    """获取指定类型的画像版本历史列表"""
    if type not in ("detailed", "deep"):
        raise HTTPException(status_code=400, detail="type 参数必须为 detailed 或 deep")
    versions = await get_portrait_versions(type)
    return versions


@router.get("/versions/{version_id}")
async def api_get_portrait_version(version_id: str):
    """获取指定 ID 的画像版本详情"""
    version = await get_portrait_version_by_id(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="画像版本不存在")
    return version


@router.post("/generate/yearly")
async def api_generate_yearly_profile(
    year: Optional[int] = Query(default=None, description="年份，默认为当前年"),
):
    """触发年画像生成"""
    from app.services.compiler import generate_yearly_profile

    result = await generate_yearly_profile(year=year)
    return result


@router.post("/generate/core")
async def api_generate_core_personality():
    """触发核心人格档案生成"""
    from app.services.compiler import generate_core_personality

    result = await generate_core_personality()
    return result


@router.post("/generate/recent")
async def api_generate_recent_dynamics():
    """触发近期动态画像生成"""
    from app.services.compiler import generate_recent_dynamics

    result = await generate_recent_dynamics()
    return result


@router.get("/core")
async def api_get_core_personality():
    """获取核心人格档案"""
    async with get_connection() as db:
        row = await db.execute_fetchall(
            "SELECT compiled_truth, summary FROM pages WHERE slug = ?",
            ["core_personality"],
        )
    if not row:
        raise HTTPException(status_code=404, detail="核心人格档案不存在")
    return {"compiled_truth": row[0]["compiled_truth"], "summary": row[0]["summary"]}


@router.get("/recent")
async def api_get_recent_dynamics():
    """获取近期动态画像"""
    async with get_connection() as db:
        row = await db.execute_fetchall(
            "SELECT compiled_truth, summary FROM pages WHERE slug LIKE 'recent_dynamics_%' ORDER BY created_at DESC LIMIT 1",
        )
    if not row:
        raise HTTPException(status_code=404, detail="近期动态画像不存在")
    return {"compiled_truth": row[0]["compiled_truth"], "summary": row[0]["summary"]}


# NOTE: /{profile_id} must be LAST — FastAPI matches routes in order,
# and this catch-all path would shadow /conflicts, /core, /recent, etc.
@router.get("/{profile_id}", response_model=ProfileFragment)
async def api_get_profile(profile_id: str):
    fragment = await get_profile_by_id(profile_id)
    if fragment is None:
        raise HTTPException(status_code=404, detail="画像片段不存在")
    return fragment
