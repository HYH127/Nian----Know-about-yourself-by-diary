from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import datetime

import structlog

from app.config import settings
from app.database import get_connection
from app.models.profile import ProfileFragment
from app.prompts.profile_extraction import (
    PROFILE_EXTRACTION_PROMPT,
    DECISION_SUB_PROFILE_PROMPT,
)
from app.prompts.change_narrative import CHANGE_NARRATIVE_PROMPT
from app.services.signal_extractor import Signal
from app.services.vector_store import vector_store
from app.utils.embedding import embed_text, embed_texts
from app.utils.llm import chat_completion

logger = structlog.get_logger()

VALID_CONFIDENCE_LEVELS = {"explicit", "frequent", "implied", "inferred"}


def _parse_profile_response(raw: str) -> list[dict]:
    json_str = raw
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()

    try:
        items = json.loads(json_str)
    except json.JSONDecodeError:
        array_match = re.search(r"\[.*\]", json_str, re.DOTALL)
        if array_match:
            try:
                items = json.loads(array_match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(items, list):
        return []

    return [item for item in items if isinstance(item, dict)]


def _validate_fragment(item: dict) -> dict | None:
    confidence = item.get("confidence", "inferred")
    if confidence not in VALID_CONFIDENCE_LEVELS:
        confidence = "inferred"

    item["confidence"] = confidence

    return item


async def build_profiles_from_signals(
    signals: list[Signal], source_type: str, source_id: str
) -> list[ProfileFragment]:
    """从信号构建画像片段"""
    signals_by_type: dict[str, list[Signal]] = defaultdict(list)
    for sig in signals:
        signals_by_type[sig.type].append(sig)

    signals_text = json.dumps(
        [
            {
                "type": s.type,
                "content": s.content,
                "evidence": s.evidence,
                "sub_type": s.sub_type,
                "media_info": s.media_info,
            }
            for s in signals
        ],
        ensure_ascii=False,
        indent=2,
    )

    existing_profiles = await _get_existing_profiles_summary()

    prompt = PROFILE_EXTRACTION_PROMPT.format(
        existing_profiles=existing_profiles,
        signals=signals_text,
    )
    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="画像维度提取",
    )

    parsed = _parse_profile_response(raw)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fragments: list[ProfileFragment] = []
    for item in parsed:
        validated = _validate_fragment(item)
        if validated is None:
            continue

        evidence_list = validated.get("evidence", [])
        if isinstance(evidence_list, str):
            evidence_list = [evidence_list]

        fragments.append(ProfileFragment(
            id=uuid.uuid4().hex,
            content=validated.get("content", ""),
            confidence=validated["confidence"],
            evidence=evidence_list,
            frequency=1,
            first_seen=now,
            last_updated=now,
            is_active=True,
            trigger=validated.get("trigger"),
            behavior=validated.get("behavior"),
            source=f"{source_type}:{source_id}",
        ))

    return fragments


async def extract_decision_sub_profiles(
    signals: list[Signal],
) -> list[ProfileFragment]:
    """从决策信号中提取四个子维度画像，仅在检测到 >=3 次明确决策事件时触发"""
    decision_signals = [s for s in signals if s.type == "decision"]
    if not decision_signals:
        return []

    hesitation_count = sum(1 for s in decision_signals if s.sub_type == "hesitation")
    decision_count = sum(1 for s in decision_signals if s.sub_type == "decision")
    regret_count = sum(1 for s in decision_signals if s.sub_type == "regret")
    total_decisions = hesitation_count + decision_count

    if total_decisions < settings.decision_pattern.min_decisions:
        logger.info(
            "决策事件不足，跳过决策子维度提取",
            total=total_decisions,
            required=settings.decision_pattern.min_decisions,
        )
        return []

    decision_signals_text = json.dumps(
        [
            {
                "sub_type": s.sub_type,
                "content": s.content,
                "evidence": s.evidence,
                "timestamp": s.timestamp,
            }
            for s in decision_signals
        ],
        ensure_ascii=False,
        indent=2,
    )

    prompt = DECISION_SUB_PROFILE_PROMPT.format(
        decision_signals=decision_signals_text,
        hesitation_count=hesitation_count,
        decision_count=decision_count,
        regret_count=regret_count,
        total_decisions=total_decisions,
    )

    raw = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=20000,
        purpose="画像变化检测",
    )

    parsed = _parse_profile_response(raw)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fragments: list[ProfileFragment] = []
    for item in parsed:
        validated = _validate_fragment(item)
        if validated is None:
            continue

        evidence_list = validated.get("evidence", [])
        if isinstance(evidence_list, str):
            evidence_list = [evidence_list]

        fragments.append(ProfileFragment(
            id=uuid.uuid4().hex,
            content=validated.get("content", ""),
            confidence=validated["confidence"],
            evidence=evidence_list,
            frequency=1,
            first_seen=now,
            last_updated=now,
            is_active=True,
            source="decision_sub_profile",
        ))

    return fragments


async def _get_existing_profiles_summary() -> str:
    """获取已有画像的摘要文本"""
    try:
        results = await vector_store.search_profiles(
            query_vector=[0.0] * settings.llm.embedding_dimensions,
            limit=50,
            filter_dict={"is_active": True},
        )
        if not results:
            return "暂无已有画像"
        summaries = []
        for r in results:
            content = r.get("content", "")
            summaries.append(f"- {content}")
        return "\n".join(summaries)
    except Exception:
        return "暂无已有画像"


async def save_profile(fragment: ProfileFragment) -> None:
    """保存画像片段到 LanceDB"""
    vectors = await embed_texts([fragment.content])
    vector = vectors[0]
    await vector_store.add_profile(fragment, vector)


async def update_existing_profiles(
    new_signals: list[Signal],
) -> list[ProfileFragment]:
    """用新信号更新已有画像"""
    new_fragments = await build_profiles_from_signals(
        new_signals,
        new_signals[0].source_type if new_signals else "",
        new_signals[0].source_id if new_signals else "",
    )

    decision_fragments = await extract_decision_sub_profiles(new_signals)
    new_fragments.extend(decision_fragments)

    for fragment in new_fragments:
        await _check_and_deactivate_conflicting(fragment)

    # 画像更新后使快照缓存失效
    from app.services.snapshot import invalidate_snapshot
    invalidate_snapshot()

    return new_fragments


async def _check_and_deactivate_conflicting(fragment: ProfileFragment) -> None:
    """检查已有画像，冲突则标记为不活跃并生成变化叙事"""
    try:
        query_vector = await embed_text(fragment.content)
        results = await vector_store.search_profiles(
            query_vector=query_vector,
            limit=10,
            filter_dict={
                "is_active": True,
            },
        )

        for result in results:
            old_id = result.get("id", "")
            if not old_id:
                continue

            change_narrative = await _generate_change_narrative(
                old_content=result.get("content", ""),
                new_evidence=fragment.content,
            )

            metadata_str = result.get("metadata", "")
            metadata = {}
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            metadata["change_narrative"] = change_narrative

            await vector_store.update_profile(old_id, {
                "is_active": False,
                "superseded_by": fragment.id,
                "metadata": json.dumps(metadata, ensure_ascii=False),
            })

            await _save_change_narrative_to_db(
                change_type="trait_shift",
                description=change_narrative,
                trigger_profile_ids=[old_id, fragment.id],
            )

            logger.info(
                "画像冲突，旧画像已标记为不活跃",
                old_id=old_id,
                new_id=fragment.id,
            )
    except Exception:
        logger.exception("检查画像冲突失败")


async def _generate_change_narrative(
    old_content: str, new_evidence: str
) -> str:
    """调用 LLM 生成变化叙事"""
    try:
        prompt = CHANGE_NARRATIVE_PROMPT.format(
            change_type="trait_shift",
            old_content=old_content,
            new_evidence=new_evidence,
        )
        narrative = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=20000,
            purpose="画像叙事生成",
        )
        return narrative.strip()
    except Exception:
        logger.exception("生成变化叙事失败")
        return f"从「{old_content}」变为「{new_evidence}」"


async def _save_change_narrative_to_db(
    change_type: str,
    description: str,
    trigger_profile_ids: list[str],
) -> str:
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
                change_type,
                description,
                json.dumps(trigger_profile_ids),
            ),
        )
        await db.commit()
    return change_id


async def search_relevant_profiles(
    query: str, limit: int = 5
) -> list[ProfileFragment]:
    """基于查询文本检索相关画像片段"""
    query_vector = await embed_text(query)

    results = await vector_store.search_profiles(
        query_vector=query_vector,
        limit=limit,
        filter_dict={"is_active": True},
    )

    fragments: list[ProfileFragment] = []
    for r in results:
        evidence = r.get("evidence", [])
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                evidence = [evidence]

        fragments.append(ProfileFragment(
            id=r.get("id", ""),
            content=r.get("content", ""),
            confidence=r.get("confidence", "inferred"),
            evidence=evidence if isinstance(evidence, list) else [],
            frequency=r.get("frequency", 1),
            first_seen=r.get("first_seen", ""),
            last_updated=r.get("last_updated", ""),
            is_active=r.get("is_active", True),
            superseded_by=r.get("superseded_by") or None,
            trigger=r.get("trigger") or None,
            behavior=r.get("behavior") or None,
            context=r.get("context") or None,
            related_entity=r.get("related_entity") or None,
            relation_type=r.get("relation_type") or None,
            source=r.get("source") or None,
            metadata=r.get("metadata") or None,
        ))

    return fragments


def _row_to_fragment(r: dict) -> ProfileFragment:
    evidence = r.get("evidence", [])
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except json.JSONDecodeError:
            evidence = [evidence]

    return ProfileFragment(
        id=r.get("id", ""),
        content=r.get("content", ""),
        confidence=r.get("confidence", "inferred"),
        evidence=evidence if isinstance(evidence, list) else [],
        frequency=r.get("frequency", 1),
        first_seen=r.get("first_seen", ""),
        last_updated=r.get("last_updated", ""),
        is_active=r.get("is_active", True),
        superseded_by=r.get("superseded_by") or None,
        trigger=r.get("trigger") or None,
        behavior=r.get("behavior") or None,
        context=r.get("context") or None,
        related_entity=r.get("related_entity") or None,
        relation_type=r.get("relation_type") or None,
        source=r.get("source") or None,
        metadata=r.get("metadata") or None,
    )


async def list_profiles() -> list[ProfileFragment]:
    """列出画像片段"""
    try:
        filter_dict: dict = {"is_active": True}

        results = await vector_store.search_profiles(
            query_vector=[0.0] * settings.llm.embedding_dimensions,
            limit=200,
            filter_dict=filter_dict,
        )
        return [_row_to_fragment(r) for r in results]
    except Exception:
        logger.exception("列出画像片段失败")
        return []


async def get_profile_by_id(profile_id: str) -> ProfileFragment | None:
    """按 ID 获取画像片段"""
    try:
        result = await vector_store.get_profile(profile_id)
        if result is None:
            return None
        return _row_to_fragment(result)
    except Exception:
        logger.exception("获取画像片段失败", profile_id=profile_id)
        return None


async def get_character_summary() -> dict:
    """生成人物特质和人物面貌描述"""
    profiles = await list_profiles()
    if not profiles:
        return {
            "traits": [],
            "portrait": "暂无足够的画像数据来生成面貌描述。多写些日记吧。",
        }

    profile_texts = "\n\n".join([
        p.content
        for p in profiles
    ])

    truncated = profile_texts[:8000]

    traits_raw = await chat_completion(
        messages=[{
            "role": "system",
            "content": """你是一位敏锐的心理学家。请基于以下用户的行为画像片段，提炼出 6-8 个核心人格特质。
每个特质需包含：
- trait: 特质名称（1-4个字，如"坚韧"、"同理心强"、"完美主义"）
- weight: 权重（0-1）
- evidence: 一句话证据

返回纯 JSON 数组。如果数据不足则返回空数组 []。""",
        }, {
            "role": "user",
            "content": truncated[:4000],
        }],
        temperature=0.3,
        max_tokens=20000,
        purpose="画像特质提取",
    )

    traits = []
    try:
        parsed = json.loads(traits_raw)
        if isinstance(parsed, list):
            traits = parsed
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', traits_raw, re.DOTALL)
        if match:
            try:
                traits = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    portrait_raw = await chat_completion(
        messages=[{
            "role": "system",
            "content": """你是一位深刻的人性观察者和哲学家。请基于以下用户画像数据，撰写一段人物面貌描述。

要求：
1. 像哲学家一样，从内在到外在，剖析这个人物的精神内核
2. 描述其思维模式、情感倾向、行为习惯、社交姿态
3. 用具体的生活细节支撑抽象的人格判断
4. 语气克制而深邃，避免空洞的赞美或批评
5. 字数 300-500 字

返回纯文本，不分段标题。""",
        }, {
            "role": "user",
            "content": truncated[:5000],
        }],
        temperature=0.5,
        max_tokens=20000,
        purpose="画像深度分析",
    )

    portrait = portrait_raw.strip()[:600]

    return {
        "traits": traits,
        "portrait": portrait,
    }
