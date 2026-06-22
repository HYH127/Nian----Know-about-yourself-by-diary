"""User feedback service for profile generation.

Implements the feedback loop described in 用户反馈机制.md:
- Submit feedback with auto-calculated validity period
- Filter feedback for generation (time + relevance + consistency)
- Build prompt section from active feedback
- Auto-expire stale feedback
- Reactivate / delete feedback
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog

from app.database import get_connection, get_compile_sync_connection
from app.utils.llm import chat_completion

logger = structlog.get_logger()

# Default validity periods (days) by target_type
_VALIDITY_DAYS: dict[str, int] = {
    "weekly_profile": 30,
    "monthly_profile": 90,
    "yearly_profile": 365,
    "overall_profile": 180,
    "core_personality": 180,
    "recent_dynamics": 180,
}


async def submit_feedback(
    target_type: str,
    target_slug: str,
    error_type: str,
    correction_text: Optional[str] = None,
) -> str:
    """Submit user feedback with auto-calculated validity period."""
    feedback_id = uuid.uuid4().hex

    # Calculate default validity
    validity_days = _VALIDITY_DAYS.get(target_type, 90)
    # dislike type has no correction text, no expiry (statistics only)
    if error_type == "dislike":
        valid_until = None
    else:
        valid_until = (datetime.now() + timedelta(days=validity_days)).strftime("%Y-%m-%d %H:%M:%S")

    # Capture context snapshot (current entity state if target_slug references an entity)
    context_snapshot = await _capture_context_snapshot(target_slug)

    async with get_connection() as db:
        await db.execute(
            "INSERT INTO user_feedback (id, target_type, target_slug, error_type, correction_text, "
            "context_snapshot, is_active, valid_until) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (feedback_id, target_type, target_slug, error_type, correction_text,
             json.dumps(context_snapshot, ensure_ascii=False) if context_snapshot else None,
             valid_until),
        )
        await db.commit()

    logger.info("feedback_submitted", id=feedback_id, target_type=target_type,
                error_type=error_type, valid_until=valid_until)
    return feedback_id


async def _capture_context_snapshot(target_slug: str) -> Optional[dict]:
    """Capture the current state of the target entity for later consistency checks."""
    db = get_compile_sync_connection()
    cursor = db.execute(
        "SELECT compiled_truth, summary, frontmatter FROM pages WHERE slug = ? AND type != 'system'",
        (target_slug,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    snapshot = {
        "compiled_truth": (row["compiled_truth"] or "")[:500],
        "summary": (row["summary"] or "")[:200],
    }
    return snapshot


async def get_active_feedback(target_type: str, limit: int = 10) -> list[dict]:
    """Get active feedback for a target type (time-filtered)."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM user_feedback "
            "WHERE target_type = ? AND is_active = 1 "
            "AND (valid_until IS NULL OR valid_until > ?) "
            "AND created_at > ? "
            "ORDER BY created_at DESC LIMIT ?",
            (target_type, now_str, cutoff, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def filter_feedback_for_generation(
    target_type: str,
    generation_context: str,
) -> list[dict]:
    """Filter feedback for profile generation:
    1. Time filter (active + not expired + within 90 days)
    2. Relevance filter (using reranker)
    3. Consistency check (LLM-based)
    4. Sort by relevance, take top-5
    """
    # Step 1: Time filter
    candidates = await get_active_feedback(target_type, limit=20)
    if not candidates:
        return []

    # Filter out dislike type (no correction text, not injectable into prompt)
    candidates = [f for f in candidates if f.get("error_type") != "dislike" and f.get("correction_text")]
    if not candidates:
        return []

    # Step 2: Relevance filter using reranker
    try:
        from app.services.reranker import rerank
        rerank_candidates = [
            {"slug": f["id"], "snippet": f["correction_text"] or "", "score": 0.5}
            for f in candidates
        ]
        reranked = await rerank(generation_context, rerank_candidates, top_n=10)
        # Map rerank scores back to feedback
        score_map = {r["slug"]: r.get("_rerank_score", 0.0) for r in reranked}
        for f in candidates:
            f["_relevance_score"] = score_map.get(f["id"], 0.0)
        # Filter by relevance threshold
        candidates = [f for f in candidates if f.get("_relevance_score", 0) > 0.3]
    except Exception as e:
        logger.warning("feedback_rerank_failed", error=str(e))
        # Fallback: keep all candidates without relevance filtering
        for f in candidates:
            f["_relevance_score"] = 0.5

    if not candidates:
        return []

    # Step 3: Consistency check (LLM-based, only for feedback with context_snapshot)
    consistent_feedback = []
    for f in candidates:
        is_consistent = await _check_feedback_consistency(f)
        if is_consistent:
            consistent_feedback.append(f)
        else:
            # Auto-deactivate inconsistent feedback
            await _deactivate_feedback(f["id"], "与新实体状态不一致")
            logger.info("feedback_auto_deactivated", id=f["id"], reason="consistency_check_failed")

    # Step 4: Sort by relevance, take top-5
    consistent_feedback.sort(key=lambda x: x.get("_relevance_score", 0), reverse=True)
    return consistent_feedback[:5]


async def _check_feedback_consistency(feedback: dict) -> bool:
    """Check if feedback is still consistent with current entity state using LLM."""
    target_slug = feedback.get("target_slug", "")
    correction_text = feedback.get("correction_text", "")
    context_snapshot_str = feedback.get("context_snapshot", "")

    if not correction_text or not context_snapshot_str:
        return True  # No basis for checking, assume consistent

    # Read current entity state
    current_state = await _capture_context_snapshot(target_slug)
    if not current_state:
        # Target entity no longer exists, deactivate
        return False

    try:
        context_snapshot = json.loads(context_snapshot_str) if isinstance(context_snapshot_str, str) else context_snapshot_str
    except (json.JSONDecodeError, TypeError):
        return True

    # If the entity hasn't changed significantly, feedback is still valid
    old_truth = context_snapshot.get("compiled_truth", "")
    new_truth = current_state.get("compiled_truth", "")
    if old_truth == new_truth:
        return True

    # Use LLM to check consistency
    prompt = f"""判断用户反馈是否仍然与当前实体状态一致。

用户反馈：{correction_text}
反馈时的实体状态：{old_truth[:500]}
当前实体状态：{new_truth[:500]}

如果反馈的修正仍然成立（即当前状态仍然存在反馈指出的问题），返回 true。
如果当前状态已经改变，反馈已不再适用，返回 false。
只返回 true 或 false。"""

    try:
        from app.config import settings
        response = await chat_completion(
            model=settings.llm.chat_mini_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10,
            purpose="反馈一致性检查",
        )
        return "true" in response.lower()
    except Exception as e:
        logger.warning("feedback_consistency_check_failed", error=str(e))
        return True  # Assume consistent on error


async def _deactivate_feedback(feedback_id: str, reason: str) -> None:
    """Deactivate a feedback record."""
    async with get_connection() as db:
        await db.execute(
            "UPDATE user_feedback SET is_active = 0, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (feedback_id,),
        )
        await db.commit()


async def expire_feedback() -> int:
    """Expire feedback that has passed its valid_until date. Returns count of expired records."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as db:
        cursor = await db.execute(
            "UPDATE user_feedback SET is_active = 0, updated_at = datetime('now', 'localtime') "
            "WHERE is_active = 1 AND valid_until IS NOT NULL AND valid_until < ?",
            (now_str,),
        )
        await db.commit()
        return cursor.rowcount


async def reactivate_feedback(feedback_id: str) -> None:
    """Reactivate expired feedback with extended validity (1.5x original period)."""
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT target_type, valid_until FROM user_feedback WHERE id = ?",
            (feedback_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return

        target_type = row["target_type"]
        validity_days = _VALIDITY_DAYS.get(target_type, 90)
        extended_days = int(validity_days * 1.5)
        new_valid_until = (datetime.now() + timedelta(days=extended_days)).strftime("%Y-%m-%d %H:%M:%S")

        await db.execute(
            "UPDATE user_feedback SET is_active = 1, valid_until = ?, "
            "updated_at = datetime('now', 'localtime') WHERE id = ?",
            (new_valid_until, feedback_id),
        )
        await db.commit()


async def delete_feedback(feedback_id: str) -> None:
    """Delete a feedback record."""
    async with get_connection() as db:
        await db.execute("DELETE FROM user_feedback WHERE id = ?", (feedback_id,))
        await db.commit()


async def build_feedback_prompt_section(target_type: str, generation_context: str) -> str:
    """Build the feedback section to inject into profile generation prompts."""
    feedback_list = await filter_feedback_for_generation(target_type, generation_context)
    if not feedback_list:
        return ""

    sections = []
    sections.append("## 用户历史修正建议（按时间从近到远，请优先参考近期且未过期的建议）")

    for idx, fb in enumerate(feedback_list, 1):
        created = fb.get("created_at", "")[:10]
        valid_until = fb.get("valid_until", "")
        valid_str = valid_until[:10] if valid_until else "无期限"
        error_type = fb.get("error_type", "")
        correction = fb.get("correction_text", "")

        section = f"### {idx}. [{created}, 有效期至{valid_str}] 针对画像的修正（{error_type}）\n"
        section += f"   - 用户指出：\"{correction}\"\n"

        # Generate adoption suggestions based on error_type
        suggestion = _generate_adoption_suggestion(error_type, correction)
        if suggestion:
            section += f"   - 采纳建议：{suggestion}\n"

        section += "   - 置信度：高（用户显式修正）"
        sections.append(section)

    return "\n\n".join(sections)


def _generate_adoption_suggestion(error_type: str, correction_text: str) -> str:
    """Generate adoption suggestion based on error type."""
    suggestions = {
        "false_habit_formation": "在\"新习惯形成\"维度不要提及该习惯，可在\"习惯维持\"中描述",
        "wrong_relationship": "修正关系描述，使用用户指出的正确关系",
        "wrong_emotion": "修正情绪判断，使用用户指出的正确情绪",
        "fact_error": "按照用户修正的事实描述，不要重复原错误",
        "other": "按照用户修正内容调整描述",
    }
    return suggestions.get(error_type, "按照用户修正内容调整描述")


async def check_feedback_compliance(profile_text: str, profile_type: str) -> dict:
    """Check if generated profile complies with active user feedback.

    Returns {"compliant": bool, "violations_text": str}
    """
    feedback_list = await get_active_feedback(profile_type, limit=5)
    # Only check feedback with correction text
    relevant = [f for f in feedback_list if f.get("correction_text") and f.get("error_type") != "dislike"]
    if not relevant:
        return {"compliant": True, "violations_text": ""}

    # Build a simple check prompt
    feedback_items = []
    for fb in relevant:
        feedback_items.append(f"- 用户修正：{fb['correction_text']}（类型：{fb['error_type']}）")

    prompt = f"""检查以下画像文本是否违反了用户的修正建议。

用户修正建议：
{chr(10).join(feedback_items)}

画像文本：
{profile_text[:1500]}

如果画像文本违反了任何修正建议，返回 false 和违反的具体内容。
如果画像文本遵守了所有修正建议，返回 true。

输出JSON格式：
{{"compliant": true/false, "violations": "违反的具体描述，如果合规则为空字符串"}}"""

    try:
        from app.config import settings
        response = await chat_completion(
            model=settings.llm.chat_mini_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
            purpose="反馈合规检查",
        )
        # Parse response
        import re
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            compliant = result.get("compliant", True)
            violations = result.get("violations", "")
            return {"compliant": bool(compliant), "violations_text": violations}
    except Exception as e:
        logger.warning("feedback_compliance_check_failed", error=str(e))

    return {"compliant": True, "violations_text": ""}
