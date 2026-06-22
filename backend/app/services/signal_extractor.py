from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel

from app.config import settings
from app.prompts.signal_extraction_v2 import SIGNAL_EXTRACTION_V2_PROMPT
from app.utils.llm import chat_completion


class Signal(BaseModel):
    type: str
    content: str
    evidence: str
    timestamp: Optional[str] = None
    sub_type: Optional[str] = None
    media_info: Optional[dict] = None
    source_type: str = ""
    source_id: str = ""


async def _llm_extract(text: str, source_type: str) -> list[Signal]:
    """LLM 信号提取（唯一通道），使用 V2 Prompt 支持8类结构化输出。"""
    prompt = SIGNAL_EXTRACTION_V2_PROMPT.format(text=text, source_type=source_type)
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await chat_completion(
            messages=messages,
            model=settings.llm.chat_mini_model,
            temperature=0.2,
            max_tokens=20000,
            purpose="信号提取V2",
        )
    except Exception:
        return []

    return _parse_llm_v2_output(raw, source_type)


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


def _parse_llm_v2_output(raw: str, source_type: str) -> list[Signal]:
    """解析 V2 输出，将 detail 字段映射到 Signal 的 media_info 字段。"""
    items = _parse_json_array(raw)
    signals: list[Signal] = []

    for item in items:
        # 将各类 detail 字段统一映射到 media_info（Signal 模型的扩展字段）
        media_info = item.get("media_info") or item.get("expense_detail") or item.get("decision_detail") or item.get("emotion_detail") or item.get("relationship_detail") or item.get("goal_detail") or item.get("hesitation_detail")
        try:
            signals.append(Signal(
                type=item.get("type", "behavior"),
                content=item.get("content", ""),
                evidence=item.get("evidence", ""),
                timestamp=item.get("timestamp"),
                sub_type=item.get("sub_type"),
                media_info=media_info,
                source_type=source_type,
                source_id="",
            ))
        except Exception:
            continue

    return signals


async def extract_signals(text: str, source_type: str, source_id: str) -> list[Signal]:
    """纯 LLM 信号提取，不再使用正则降级。"""
    try:
        signals = await _llm_extract(text, source_type)
    except Exception:
        signals = []

    signals = await _filter_major_purchases(signals)

    for sig in signals:
        sig.source_type = source_type
        sig.source_id = source_id

    return signals


async def _filter_major_purchases(signals: list[Signal]) -> list[Signal]:
    """过滤重大消费信号：金额超过平均消费的3倍才标记"""
    from app.database import get_connection

    purchase_signals = [s for s in signals if s.sub_type == "major_purchase"]
    if not purchase_signals:
        return signals

    try:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT AVG(amount) as avg_amount FROM ("
                "  SELECT CAST(json_extract(media_info, '$.amount') AS REAL) as amount "
                "  FROM ("
                "    SELECT signal_data FROM extracted_signals WHERE sub_type = 'major_purchase'"
                "  )"
                ") WHERE amount > 0"
            )
            row = await cursor.fetchone()
            avg_amount = row["avg_amount"] if row and row["avg_amount"] else 0
    except Exception:
        avg_amount = 0

    threshold_ratio = settings.decision_pattern.major_purchase_threshold_ratio
    result = []
    for sig in signals:
        if sig.sub_type == "major_purchase" and sig.media_info:
            amount = sig.media_info.get("amount", 0)
            if avg_amount > 0 and amount < avg_amount * threshold_ratio:
                continue
        result.append(sig)

    return result
