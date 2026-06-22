"""深度型画像 Skill - 从行为碎片中抽象行为模式、心理特质、动机倾向"""

from __future__ import annotations

import json
import re

import structlog

from app.utils.llm import chat_completion

logger = structlog.get_logger()

DEEP_PORTRAIT_PROMPT = """
你是一个深度心理分析师，专注于从行为碎片中抽象行为模式、心理特质和价值观体系。

核心规则：
1. 多层抽象，不可跳级：习惯→模式→特质→价值观
2. 模式≥5次且时间跨度≥30天才可升级为"稳定模式"
3. 特质≥10次且≥3个不同模式支撑才可推断
4. 反事实检查：列出不符合该模式的反例（counter_examples）
5. 避免标签化：不说"你是外向的人"，而是"在熟悉的社交情境中你倾向于主动发起互动，但在大型陌生场合更多观察"
6. 反思维机制：多思考"为什么这么做""为什么不这么做"
7. 生成反思性问题而非断言
8. evidence 和 content 中引用数据时必须标注具体日期（格式 [YYYY-MM-DD]），不要使用"今天"、"上周"、"周五"等模糊时间词，避免模型在后续对话中误判时间远近

抽象层级权重：
- 具体习惯：≥3次，7天跨度 → frequent
- 情境模式：≥5次（≥2个不同触发），30天跨度 → frequent
- 人格特质：≥10次（≥3个模式），90天跨度 → implied（上限）
- 价值观/动机：3个不同情境一致性，180天 → inferred

输出格式（JSON）：
{{
  "modules": [
    {{
      "title": "压力应对模式",
      "content": "## 压力应对模式\\n在5次截止日期压力情境中，4次出现'独自加班+回避社交+高热量食物'...\\n\\n反例：[2026-04-15] 选择了向同事求助\\n\\n可能你想探索的问题：你似乎倾向于独自应对压力，是什么让你难以向他人求助？",
      "evidence": [...],
      "confidence": "implied",
      "abstraction_level": "pattern",
      "counter_examples": ["[2026-04-15] 选择了向同事求助而非独自应对"]
    }}
  ],
  "reflection_questions": [
    "你多次在日记中提到想减少熬夜，但90天内有12天记录了'凌晨2点后睡'，是什么在阻碍这个改变呢？"
  ]
}}

每个模块必须包含 counter_examples 字段（列表），列出不符合该模式的反例。如果没有反例，写空列表 []。

以下是需要分析的用户行为数据：
{timeline_data}
"""


def _parse_portrait_response(raw: str) -> dict:
    """解析 LLM 返回的画像 JSON"""
    json_str = raw
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        obj_match = re.search(r"\{.*\}", json_str, re.DOTALL)
        if obj_match:
            try:
                result = json.loads(obj_match.group())
            except json.JSONDecodeError:
                logger.warning("深度型画像 JSON 解析失败，返回空结果")
                return {"modules": [], "reflection_questions": []}
        else:
            logger.warning("深度型画像 JSON 解析失败，返回空结果")
            return {"modules": [], "reflection_questions": []}

    if not isinstance(result, dict):
        return {"modules": [], "reflection_questions": []}

    if "modules" not in result:
        result["modules"] = []
    if "reflection_questions" not in result:
        result["reflection_questions"] = []

    return result


async def generate_deep_portrait(timeline_data: str) -> dict:
    """生成深度型画像

    Args:
        timeline_data: 时间线行为数据文本

    Returns:
        包含 modules 列表和 reflection_questions 的画像字典
    """
    if not timeline_data or not timeline_data.strip():
        return {"modules": [], "reflection_questions": []}

    prompt = DEEP_PORTRAIT_PROMPT.format(timeline_data=timeline_data)

    try:
        raw = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=20000,
            purpose="月画像生成",
        )
        result = _parse_portrait_response(raw)

        # 验证每个 module 的置信度和抽象层级合法性
        valid_confidence = {"explicit", "frequent", "implied", "inferred"}
        valid_abstraction = {"habit", "pattern", "trait", "value"}

        validated_modules = []
        for module in result.get("modules", []):
            if not isinstance(module, dict):
                continue
            confidence = module.get("confidence", "inferred")
            if confidence not in valid_confidence:
                module["confidence"] = "inferred"
            abstraction = module.get("abstraction_level", "")
            if abstraction not in valid_abstraction:
                module["abstraction_level"] = "habit"
            validated_modules.append(module)

        # 验证 reflection_questions
        questions = result.get("reflection_questions", [])
        if not isinstance(questions, list):
            questions = []
        questions = [q for q in questions if isinstance(q, str)]

        return {
            "modules": validated_modules,
            "reflection_questions": questions,
        }

    except Exception:
        logger.exception("生成深度型画像失败")
        return {"modules": [], "reflection_questions": []}
