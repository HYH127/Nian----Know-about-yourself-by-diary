from __future__ import annotations

import csv
import io
import json
import re

import structlog

from app.services.importer.consumption_base import classify_category
from app.utils.llm import chat_completion

logger = structlog.get_logger()


def parse_consumption_csv(file_content: str, source: str) -> list[dict]:
    """Parse CSV into structured items (date, merchant, amount, category).

    Supports alipay and wechat_pay source formats.
    """
    reader = csv.DictReader(io.StringIO(file_content))
    items = []

    for row in reader:
        if source == "alipay":
            if row.get("收支类型", "") != "支出" or "成功" not in row.get("交易状态", ""):
                continue
            try:
                amount = float(row.get("金额", 0))
            except (ValueError, TypeError):
                amount = 0
            merchant = row.get("交易对方", "")
            description = row.get("商品说明", "")
            date = row.get("交易时间", "")
        elif source == "wechat_pay":
            if "成功" not in row.get("当前状态", ""):
                continue
            try:
                amount = float(row.get("金额", 0))
            except (ValueError, TypeError):
                amount = 0
            if amount <= 0:
                continue
            merchant = row.get("交易对方", "")
            description = row.get("商品", "")
            date = row.get("交易时间", "")
        else:
            continue

        category = classify_category(merchant, description)
        items.append({
            "date": date,
            "merchant": merchant,
            "description": description,
            "amount": amount,
            "category": category,
        })

    return items


async def infer_habits_from_consumption(items: list[dict]) -> list[dict]:
    """Use LLM to analyze consumption patterns and infer user habits.

    Returns list of inferred habits with evidence.
    If insufficient data for inference, returns empty list.
    """
    if len(items) < 3:
        return []

    # Build a concise summary for the LLM
    summary_lines = []
    for item in items[:200]:  # limit to avoid token overflow
        summary_lines.append(
            f"- {item['date']} | {item['merchant']} | ¥{item['amount']:.2f} | {item['category']}"
        )
    consumption_text = "\n".join(summary_lines)

    prompt = f"""你是一个消费习惯分析专家。请根据以下消费记录，识别用户的消费习惯和模式。

要求：
1. 只识别有明显规律性的习惯（例如：每天早上买咖啡、每周点外卖、每月固定消费等）
2. 每个习惯需要提供证据（具体消费记录支撑）
3. 如果数据不足以推断出明确习惯，返回空数组
4. 返回 JSON 格式

消费记录：
{consumption_text}

请返回如下 JSON 格式（不要包含其他文字）：
```json
[
  {{
    "habit": "习惯描述",
    "evidence": "支撑证据",
    "category": "消费类别",
    "frequency": "频率描述（如：每天、每周、每月）"
  }}
]
```"""

    try:
        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=20000,
            purpose="消费习惯推断",
        )

        # Parse JSON from response
        json_str = response
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", response, re.DOTALL)
        if fence_match:
            json_str = fence_match.group(1).strip()

        obj_match = re.search(r"\[.*\]", json_str, re.DOTALL)
        if obj_match:
            habits = json.loads(obj_match.group())
            if isinstance(habits, list):
                return habits

        return []
    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.warning("消费习惯推断失败", error=str(e))
        return []


async def confirm_and_write_habits(confirmed_habits: list[dict]) -> int:
    """Write confirmed habits to knowledge base as habit entities.

    Returns the number of habits written.
    """
    if not confirmed_habits:
        return 0

    from app.services.knowledge import create_knowledge_item

    count = 0
    for habit in confirmed_habits:
        try:
            await create_knowledge_item({
                "title": f"消费习惯：{habit.get('habit', '未知习惯')}",
                "type": "habit",
                "summary": habit.get("habit", ""),
                "user_notes": f"证据：{habit.get('evidence', '')}；频率：{habit.get('frequency', '')}；类别：{habit.get('category', '')}",
            })
            count += 1
        except Exception as e:
            logger.warning("写入习惯失败", habit=habit.get("habit", ""), error=str(e))

    return count
