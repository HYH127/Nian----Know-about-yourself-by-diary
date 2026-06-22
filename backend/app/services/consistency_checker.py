"""Consistency checker module for the supervisor agent.

Provides three core checks:
1. Entity consistency — after compile_entity, check new truth vs related entities
2. Profile quality — score profile text against source materials
3. Cross-profile consistency — check new profile vs existing profiles
"""

from __future__ import annotations

import json
import re

import structlog
from pydantic import BaseModel

from app.prompts.consistency_check import (
    ENTITY_CONSISTENCY_PROMPT,
    PROFILE_QUALITY_PROMPT,
    CROSS_PROFILE_CONSISTENCY_PROMPT,
)
from app.utils.llm import chat_completion

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ConflictItem(BaseModel):
    entity: str
    conflict_description: str = ""
    old_statement: str = ""
    new_statement: str = ""


class ConsistencyResult(BaseModel):
    has_conflict: bool = False
    conflicts: list[ConflictItem] = []
    suggested_action: str = "none"  # none | flag | auto_resolve | user_confirm


class QualityResult(BaseModel):
    score: float = 1.0
    issues: list[str] = []
    suggestions: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    m = re.search(r'```(?:json)?\s*(\{.+?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return {}


def _read_related_entity_truths(entity_tag: str) -> str:
    """Read compiled_truth of entities related to the given entity."""
    from app.services.compiler import get_compile_sync_connection

    db = get_compile_sync_connection()

    # Find the entity's related_entities from frontmatter
    cursor = db.execute(
        "SELECT frontmatter FROM pages WHERE slug = ? AND type != 'system'",
        (entity_tag,),
    )
    row = cursor.fetchone()
    if not row:
        return ""

    try:
        fm = json.loads(row["frontmatter"]) if row["frontmatter"] else {}
    except (json.JSONDecodeError, TypeError):
        return ""

    related_entities = fm.get("related_entities", [])
    if not isinstance(related_entities, list):
        return ""

    related_slugs = []
    for entry in related_entities:
        if not isinstance(entry, str):
            continue
        m = re.match(r'\[\[(.+?)\]\]', entry)
        if m:
            ref = m.group(1)
            slug = ref.split(':', 1)[1] if ':' in ref else ref
            related_slugs.append(slug)

    if not related_slugs:
        return ""

    # Read compiled_truth of related entities
    placeholders = ",".join("?" for _ in related_slugs)
    cursor = db.execute(
        f"SELECT slug, title, compiled_truth FROM pages WHERE slug IN ({placeholders}) AND type != 'system' AND compiled_truth != ''",
        related_slugs,
    )

    parts = []
    for row in cursor.fetchall():
        parts.append(f"- {row['title']}({row['slug']}): {row['compiled_truth'][:300]}")

    return "\n".join(parts[:10])


def _read_existing_profiles(profile_type: str) -> str:
    """Read existing profiles of the same or parent type for cross-profile checks."""
    from app.services.compiler import get_compile_sync_connection

    db = get_compile_sync_connection()

    slug_patterns = {
        "weekly": ["weekly_profile_%"],
        "monthly": ["monthly_profile_%", "weekly_profile_%"],
        "yearly": ["yearly_profile_%", "monthly_profile_%"],
        "overall": ["monthly_profile_%", "yearly_profile_%"],
        "core": ["monthly_profile_%", "yearly_profile_%"],
        "recent": ["monthly_profile_%", "weekly_profile_%"],
    }

    patterns = slug_patterns.get(profile_type, ["monthly_profile_%"])
    parts = []

    for pattern in patterns:
        cursor = db.execute(
            "SELECT slug, compiled_truth FROM pages WHERE type = 'system' "
            "AND slug LIKE ? AND compiled_truth != '' ORDER BY slug DESC LIMIT 3",
            (pattern,),
        )
        for row in cursor.fetchall():
            parts.append(f"[{row['slug']}] {row['compiled_truth'][:500]}")

    return "\n\n".join(parts[:6])


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------

async def check_entity_consistency(entity_tag: str, new_truth: str) -> ConsistencyResult:
    """Check if the newly compiled entity truth conflicts with related entities."""
    related_truths = await _read_related_async(entity_tag)

    if not related_truths.strip():
        return ConsistencyResult(has_conflict=False)

    prompt = ENTITY_CONSISTENCY_PROMPT.format(
        entity_tag=entity_tag,
        new_truth=new_truth[:1500],
        related_truths=related_truths[:2000],
    )

    try:
        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=20000,
            purpose="实体一致性检查",
        )
        parsed = _parse_json_response(response)

        if not parsed.get("has_conflict", False):
            return ConsistencyResult(has_conflict=False)

        conflicts = []
        for c in parsed.get("conflicts", []):
            conflicts.append(ConflictItem(
                entity=c.get("entity", ""),
                conflict_description=c.get("description", c.get("conflict_description", "")),
                old_statement=c.get("old_statement", ""),
                new_statement=c.get("new_statement", ""),
            ))

        return ConsistencyResult(
            has_conflict=True,
            conflicts=conflicts,
            suggested_action=parsed.get("suggested_action", "flag"),
        )

    except Exception as e:
        logger.error("entity_consistency_check_error", entity=entity_tag, error=str(e))
        return ConsistencyResult(has_conflict=False)


async def _read_related_async(entity_tag: str) -> str:
    """Async wrapper for _read_related_entity_truths."""
    import asyncio
    return await asyncio.to_thread(_read_related_entity_truths, entity_tag)


async def check_profile_quality(
    profile_text: str,
    source_materials: str,
    profile_type: str,
) -> QualityResult:
    """Score profile quality against source materials."""
    prompt = PROFILE_QUALITY_PROMPT.format(
        profile_type=profile_type,
        profile_text=profile_text[:2000],
        source_materials=source_materials[:2000],
    )

    try:
        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=20000,
            purpose="画像质量评价",
        )
        parsed = _parse_json_response(response)

        return QualityResult(
            score=float(parsed.get("score", 1.0)),
            issues=parsed.get("issues", []),
            suggestions=parsed.get("suggestions", []),
        )

    except Exception as e:
        logger.error("profile_quality_check_error", profile_type=profile_type, error=str(e))
        return QualityResult(score=1.0)  # Default to pass on error


async def check_cross_profile_consistency(
    new_profile: str,
    profile_type: str,
) -> ConsistencyResult:
    """Check if a new profile conflicts with existing profiles."""
    import asyncio

    existing_profiles = await asyncio.to_thread(_read_existing_profiles, profile_type)

    if not existing_profiles.strip():
        return ConsistencyResult(has_conflict=False)

    prompt = CROSS_PROFILE_CONSISTENCY_PROMPT.format(
        profile_type=profile_type,
        new_profile=new_profile[:2000],
        existing_profiles=existing_profiles[:2000],
    )

    try:
        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=20000,
            purpose="跨画像一致性检查",
        )
        parsed = _parse_json_response(response)

        if not parsed.get("has_conflict", False):
            return ConsistencyResult(has_conflict=False)

        conflicts = []
        for c in parsed.get("conflicts", []):
            conflicts.append(ConflictItem(
                entity=c.get("entity", ""),
                conflict_description=c.get("conflict_description", c.get("description", "")),
                old_statement=c.get("old_statement", ""),
                new_statement=c.get("new_statement", ""),
            ))

        return ConsistencyResult(
            has_conflict=True,
            conflicts=conflicts,
            suggested_action=parsed.get("suggested_action", "flag"),
        )

    except Exception as e:
        logger.error("cross_profile_consistency_error", profile_type=profile_type, error=str(e))
        return ConsistencyResult(has_conflict=False)
