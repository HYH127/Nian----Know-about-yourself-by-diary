"""细致型画像 Skill - 捕捉具体偏好、习惯细节、关系亲密度、消费品味"""

from __future__ import annotations

import json
import re

import structlog

from app.utils.llm import chat_completion

logger = structlog.get_logger()

DETAILED_PORTRAIT_PROMPT = """
你是一个用户画像分析师，专注于从行为数据中提取具体偏好和习惯细节。

分析规则：
1. 从 Timeline 中挖掘重复 ≥3 次的相同选择（如"每次都点拿铁"）
2. 标注每次出现的来源和时间，计算频率
3. 若用户曾明确表达偏好（如"还是这家最好吃"），提升置信度
4. 对新出现的偏好标记为"近期新偏好"
5. 时间权重：最近7天×3.0, 8-30天×2.0, 31-90天×1.0, 91-365天×0.5, 1年以上×0.3
6. 防抖：新信号出现后，连续3次确认才更新"当前偏好"；单次异常不触发更改
7. evidence 和 content 中引用数据时必须标注具体日期（格式 [YYYY-MM-DD]），不要使用"今天"、"上周"、"周五"等模糊时间词，避免模型在后续对话中误判时间远近

输出格式（JSON）：
{{
  "modules": [
    {{
      "title": "日常小偏好",
      "content": "## 日常小偏好\\n- 咖啡：拿铁（冰），近期常去XX咖啡馆（近30天6次）\\n- 运动：跑步后必买椰子水（证据：3/3次跑步后消费记录）\\n...",
      "evidence": ["diary/2026-06-01", "consumption/2026-05"],
      "confidence": "frequent"
    }}
  ]
}}

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
        # 尝试提取 JSON 对象
        obj_match = re.search(r"\{.*\}", json_str, re.DOTALL)
        if obj_match:
            try:
                result = json.loads(obj_match.group())
            except json.JSONDecodeError:
                logger.warning("细致型画像 JSON 解析失败，返回空结果")
                return {"modules": []}
        else:
            logger.warning("细致型画像 JSON 解析失败，返回空结果")
            return {"modules": []}

    if not isinstance(result, dict) or "modules" not in result:
        return {"modules": []}

    return result


async def generate_detailed_portrait(timeline_data: str) -> dict:
    """生成细致型画像

    Args:
        timeline_data: 时间线行为数据文本

    Returns:
        包含 modules 列表的画像字典
    """
    if not timeline_data or not timeline_data.strip():
        return {"modules": []}

    prompt = DETAILED_PORTRAIT_PROMPT.format(timeline_data=timeline_data)

    try:
        raw = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=20000,
            purpose="周画像生成",
        )
        result = _parse_portrait_response(raw)

        # 验证每个 module 的置信度合法性
        valid_confidence = {"explicit", "frequent", "implied", "inferred"}

        validated_modules = []
        for module in result.get("modules", []):
            if not isinstance(module, dict):
                continue
            confidence = module.get("confidence", "inferred")
            if confidence not in valid_confidence:
                module["confidence"] = "inferred"
            validated_modules.append(module)

        return {"modules": validated_modules}

    except Exception:
        logger.exception("生成细致型画像失败")
        return {"modules": []}
