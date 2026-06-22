from __future__ import annotations

import json
import re

from app.database import get_connection
from app.utils.llm import chat_completion

_EXPENSE_PATTERNS = [
    (re.compile(r"(花了|买了|消费了?|花费了?|用了)\s*(\d+[\d,.]*)\s*(元|块|块钱|万元|万块)"), "shopping"),
    (re.compile(r"(花了|买了|消费了?|花费了?|用了)([一二三四五六七八九十百千万亿]+)\s*(元|块|块钱)"), "shopping"),
]

_DECISION_RE = re.compile(r"(决定|选择|最终选了|下定决心|做出决定|下定决心)")

_EMOTION_POSITIVE_RE = re.compile(r"(开心|高兴|兴奋|满足|幸福|感动|欣慰|自豪)")
_EMOTION_NEGATIVE_RE = re.compile(r"(难过|伤心|焦虑|烦躁|沮丧|失望|愤怒|疲惫|迷茫)")

_RELATIONSHIP_RE = re.compile(r"(见面|聊天|吵架|争执|和解|和好|聚餐|约会|通话|打电话)")

_GOAL_RE = re.compile(r"(目标|计划|打算|想学|想要|希望|期待)")

_REFLECTION_RE = re.compile(r"(反思|回顾|总结|意识到|明白了?|领悟|学到)")

_MAX_SIGNALS = 20


def extract_signals_regex(text: str) -> list[dict]:
    signals: list[dict] = []

    for pattern, sub_type in _EXPENSE_PATTERNS:
        for match in pattern.finditer(text):
            signals.append({
                "type": "expense",
                "sub_type": sub_type,
                "content": f"消费行为：{match.group()}",
                "evidence": match.group(),
                "source_type": "",
                "source_id": "",
            })

    for match in _DECISION_RE.finditer(text):
        signals.append({
            "type": "decision",
            "sub_type": "decision",
            "content": f"做出决策：{match.group()}",
            "evidence": match.group(),
            "source_type": "",
            "source_id": "",
        })

    for match in _EMOTION_POSITIVE_RE.finditer(text):
        signals.append({
            "type": "emotion",
            "sub_type": "positive",
            "content": f"积极情绪：{match.group()}",
            "evidence": match.group(),
            "source_type": "",
            "source_id": "",
        })

    for match in _EMOTION_NEGATIVE_RE.finditer(text):
        signals.append({
            "type": "emotion",
            "sub_type": "negative",
            "content": f"消极情绪：{match.group()}",
            "evidence": match.group(),
            "source_type": "",
            "source_id": "",
        })

    for match in _RELATIONSHIP_RE.finditer(text):
        signals.append({
            "type": "relationship",
            "sub_type": "interaction",
            "content": f"人际互动：{match.group()}",
            "evidence": match.group(),
            "source_type": "",
            "source_id": "",
        })

    for match in _GOAL_RE.finditer(text):
        signals.append({
            "type": "goal",
            "sub_type": "intention",
            "content": f"目标意愿：{match.group()}",
            "evidence": match.group(),
            "source_type": "",
            "source_id": "",
        })

    for match in _REFLECTION_RE.finditer(text):
        signals.append({
            "type": "reflection",
            "sub_type": "insight",
            "content": f"反思领悟：{match.group()}",
            "evidence": match.group(),
            "source_type": "",
            "source_id": "",
        })

    signals.sort(key=lambda s: list(text).index(s["evidence"][0]) if s["evidence"] and s["evidence"][0] in text else 0)
    return signals[:_MAX_SIGNALS]


async def extract_signals_llm(text: str) -> list[dict]:
    """LLM 驱动的信号提取（主通道），使用 V2 Prompt 支持8类结构化输出。"""
    from app.config import settings
    from app.prompts.signal_extraction_v2 import SIGNAL_EXTRACTION_V2_PROMPT

    try:
        raw = await chat_completion(
            model=settings.llm.chat_mini_model,
            messages=[{"role": "user", "content": SIGNAL_EXTRACTION_V2_PROMPT.format(text=text, source_type="")}],
            temperature=0.2,
            max_tokens=20000,
            purpose="信号提取LLM-V2",
        )
    except Exception:
        return []

    return _parse_llm_v2_response(raw)


def _parse_json_array(raw: str) -> list[dict]:
    """从 LLM 响应中解析 JSON 数组，处理 markdown 代码块和格式问题。"""
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


def _parse_llm_v2_response(raw: str) -> list[dict]:
    """解析 V2 Prompt 的结构化输出，将 detail 字段合并到 signal dict。"""
    items = _parse_json_array(raw)
    signals: list[dict] = []

    for item in items:
        sig = {
            "type": item.get("type", ""),
            "sub_type": item.get("sub_type", ""),
            "content": item.get("content", ""),
            "evidence": item.get("evidence", ""),
            "source_type": "",
            "source_id": "",
        }
        # 合并 detail 字段到顶层
        for detail_key in ["emotion_detail", "decision_detail", "expense_detail",
                           "media_info", "relationship_detail", "goal_detail", "hesitation_detail"]:
            if detail_key in item:
                sig[detail_key] = item[detail_key]
        signals.append(sig)

    return signals


def deduplicate_signals(signals: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []

    for sig in signals:
        key = f"{sig.get('type', '')}:{sig.get('sub_type', '')}:{sig.get('evidence', '')}"
        if key not in seen:
            seen.add(key)
            result.append(sig)

    return result


# Words that should NOT become entity tags (ephemeral/trivial)
_TRIVIAL_WORDS = {
    "高兴", "开心", "难过", "烦躁", "焦虑", "兴奋", "满足", "幸福", "感动",
    "欣慰", "自豪", "伤心", "沮丧", "失望", "愤怒", "疲惫", "迷茫", "后悔",
    "花了", "买了", "消费", "花费", "用了", "块", "块钱", "元", "万元",
    "吃了", "喝了", "睡了", "洗了", "去了", "来了", "做了", "看了", "听了",
    "打了", "走了", "跑了", "写了", "说了", "想了", "用了",
    "今天", "昨天", "明天", "上午", "下午", "晚上", "早上", "中午",
    "然后", "但是", "因为", "所以", "虽然", "不过", "而且", "或者",
    "同学", "室友", "老师", "朋友", "同事", "领导", "老板",
    "感觉", "觉得", "认为", "希望", "想要", "打算", "决定",
    "东西", "事情", "问题", "办法", "地方", "时候", "样子",
}


def extract_entity_tags(text: str) -> list[str]:
    words = re.split(r"[，。！？、；：\u201c\u201d\u2018\u2019（）\s\n,.!?;:'\"()]+", text)
    # Filter: 2-6 chars, not trivial, not pure numbers, not common verbs
    filtered = []
    for w in words:
        if not (2 <= len(w) <= 6):
            continue
        if w in _TRIVIAL_WORDS:
            continue
        if re.match(r'^[\d,.]+$', w):
            continue
        if re.match(r'^[了着过得地]', w):
            continue
        filtered.append(w)
    seen: set[str] = set()
    unique: list[str] = []
    for w in filtered:
        if w not in seen:
            seen.add(w)
            unique.append(w)
            if len(unique) >= 3:
                break
    return unique


async def log_signals(signals: list[dict], source_type: str = "", source_id: str = "") -> list[int]:
    ids: list[int] = []

    async with get_connection() as db:
        for sig in signals:
            signal_json = json.dumps(sig, ensure_ascii=False)
            content = sig.get("content", "")
            tags = extract_entity_tags(content)
            entity_tags = json.dumps(tags, ensure_ascii=False)

            cursor = await db.execute(
                "INSERT INTO raw_signals (signal_json, entity_tags, status, source_type, source_id) "
                "VALUES (?, ?, 'unprocessed', ?, ?)",
                (signal_json, entity_tags, source_type, source_id),
            )
            await db.commit()
            ids.append(cursor.lastrowid)

    return ids


async def extract_and_log_signals(text: str, source_type: str = "", source_id: str = "") -> list[dict]:
    """LLM 为主通道，正则降级兜底。"""
    try:
        llm_signals = await extract_signals_llm(text)
    except Exception:
        llm_signals = []

    # LLM 有结果则直接使用，不再合并正则（避免重复和低质量正则结果）
    if llm_signals:
        deduped = deduplicate_signals(llm_signals)
    else:
        # LLM 失败时降级到正则
        deduped = extract_signals_regex(text)

    await log_signals(deduped, source_type=source_type, source_id=source_id)

    return deduped