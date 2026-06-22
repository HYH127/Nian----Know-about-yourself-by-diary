from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime

import structlog

from app.database import get_connection
from app.models.timeline import TimelineEventCreate
from app.services.timeline import create_timeline_event

logger = structlog.get_logger()

CATEGORY_MAP = {
    "餐饮": ["美团", "饿了么", "肯德基", "麦当劳", "星巴克", "奶茶", "火锅", "外卖", "餐厅", "饭馆", "小吃", "烧烤", "咖啡", "饮品"],
    "交通": ["滴滴", "高德", "地铁", "加油", "停车", "铁路", "航空", "打车", "公交", "共享单车", "哈啰"],
    "购物": ["淘宝", "京东", "拼多多", "天猫", "超市", "便利店", "沃尔玛", "盒马", "山姆"],
    "娱乐": ["电影", "游戏", "KTV", "酒吧", "演出", "演唱会", "剧本杀", "密室"],
    "医疗": ["医院", "药房", "体检", "诊所", "牙科", "中医"],
    "教育": ["课程", "培训", "书", "学堂", "教育", "网校"],
    "居住": ["房租", "物业", "水电", "燃气", "宽带", "装修"],
}

_AMOUNT_THRESHOLDS = {
    "小额": 50,
    "中额": 200,
    "大额": 1000,
}


def classify_category(merchant: str, description: str) -> str:
    text = f"{merchant} {description}"
    for category, keywords in CATEGORY_MAP.items():
        for keyword in keywords:
            if keyword in text:
                return category
    return "其他"


def classify_amount_level(amount: float) -> str:
    for level, threshold in _AMOUNT_THRESHOLDS.items():
        if amount <= threshold:
            return level
    return "大额"


def extract_consumption_signals(records: list[dict]) -> list[dict]:
    """提取消费信号：消费类别、时段、金额分布、商户偏好"""
    signals = []

    for record in records:
        category = classify_category(record.get("merchant", ""), record.get("description", ""))
        record["category"] = category
        amount_level = classify_amount_level(record.get("amount", 0))
        record["amount_level"] = amount_level
        signals.append(record)

    return signals


async def create_consumption_timeline_event(signal: dict, import_batch_id: str) -> None:
    """将消费信号写入时间线事件"""
    event_id = uuid.uuid4().hex
    timestamp = signal.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    summary = (
        f"消费：{signal.get('merchant', '未知商户')} - "
        f"{signal.get('description', '')} "
        f"¥{signal.get('amount', 0):.2f}（{signal.get('category', '其他')}）"
    )

    event = TimelineEventCreate(
        timestamp=timestamp,
        event_type="consumption",
        summary=summary,
        sentiment=None,
        emotional_keywords=signal.get("category", ""),
        related_dimensions="behavior_habit,interest_taste",
        related_contacts="",
        related_events="",
        source_type="consumption",
        source_id=f"{signal.get('source', 'unknown')}:{import_batch_id}:{event_id}",
        importance_score=0.6 if signal.get("amount_level") == "大额" else 0.3,
        is_milestone=signal.get("amount", 0) >= 1000,
    )

    await create_timeline_event(event)


async def aggregate_consumption_stats(records: list[dict], import_batch_id: str) -> None:
    """汇总消费统计并写入时间线"""
    if not records:
        return

    category_counter: Counter = Counter()
    amount_by_category: defaultdict = defaultdict(float)
    hourly_counter: Counter = Counter()
    merchant_counter: Counter = Counter()
    total_amount = 0.0

    for record in records:
        category = record.get("category", "其他")
        amount = record.get("amount", 0)
        category_counter[category] += 1
        amount_by_category[category] += amount
        total_amount += amount
        merchant_counter[record.get("merchant", "")] += 1

        ts = record.get("timestamp", "")
        if ts and len(ts) >= 13:
            try:
                hour = int(ts[11:13])
                hourly_counter[hour] += 1
            except (ValueError, IndexError):
                pass

    top_category = category_counter.most_common(1)[0][0] if category_counter else "其他"
    top_merchant = merchant_counter.most_common(1)[0][0] if merchant_counter else ""

    summary = (
        f"消费汇总：共 {len(records)} 笔支出，"
        f"总金额 ¥{total_amount:.2f}，"
        f"主要类别「{top_category}」，"
        f"常去商户「{top_merchant}」"
    )

    event = TimelineEventCreate(
        timestamp=records[0].get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        event_type="consumption_summary",
        summary=summary,
        sentiment=None,
        emotional_keywords=",".join(category_counter.keys()),
        related_dimensions="behavior_habit,interest_taste,value_belief",
        related_contacts="",
        related_events="",
        source_type="consumption",
        source_id=f"summary:{import_batch_id}",
        importance_score=0.5,
        is_milestone=False,
    )

    await create_timeline_event(event)
