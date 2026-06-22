from __future__ import annotations

import asyncio
import uuid
from collections import Counter, defaultdict
from datetime import datetime

import structlog

from app.models.timeline import TimelineEventCreate
from app.services.timeline import create_timeline_event
from app.services.knowledge import extract_knowledge_from_import

logger = structlog.get_logger()

_GENRE_MAP = {
    "book": {
        "科幻": ["三体", "基地", "沙丘", "银河帝国"],
        "推理": ["嫌疑人", "白夜行", "解忧", "东野圭吾", "阿加莎"],
        "文学": ["百年孤独", "活着", "围城", "红楼梦", "平凡的世界"],
        "历史": ["明朝", "万历", "人类简史", "枪炮", "病菌"],
        "心理": ["被讨厌的勇气", "乌合之众", "思考", "快与慢"],
        "经管": ["原则", "穷查理", "巴菲特", "经济学"],
    },
    "movie": {
        "科幻": ["星际穿越", "盗梦空间", "银翼杀手", "流浪地球"],
        "喜剧": ["夏洛特", "西虹市", "飞驰人生", "唐人街"],
        "悬疑": ["消失的她", "看不见的客人", "利刃出鞘"],
        "动作": ["速度与激情", "漫威", "战狼", "红海"],
        "动画": ["宫崎骏", "新海诚", "皮克斯", "哪吒"],
        "文艺": ["花样年华", "重庆森林", "小津", "是枝裕和"],
    },
    "tv_series": {
        "悬疑": ["隐秘的角落", "沉默的真相", "漫长的季节"],
        "古装": ["甄嬛传", "琅琊榜", "庆余年", "知否"],
        "都市": ["都挺好", "小欢喜", "三十而已"],
        "美剧": ["绝命毒师", "权力的游戏", "老友记"],
        "日剧": ["非自然死亡", "半泽直树", "东京爱情故事"],
    },
    "music": {
        "流行": ["周杰伦", "陈奕迅", "林俊杰", "邓紫棋"],
        "摇滚": ["五月天", "Beyond", "新裤子", "痛仰"],
        "民谣": ["赵雷", "陈粒", "李志", "花粥"],
        "古典": ["贝多芬", "莫扎特", "肖邦", "巴赫"],
        "电子": ["A神", "烟鬼", "棉花糖"],
    },
    "podcast": {
        "科技": ["硬地骇客", "枫言枫语", "科技乱炖"],
        "文化": ["忽左忽右", "随机波动", "八分"],
        "商业": ["商业就是这样", "疯投圈", "创业内幕"],
        "生活": ["日谈公园", "无聊斋", "大内密谈"],
    },
}

_RATING_EMOTION_MAP = {
    (4.5, 5.1): "热爱",
    (3.5, 4.5): "喜爱",
    (2.5, 3.5): "中性",
    (1.5, 2.5): "失望",
    (0, 1.5): "厌恶",
}


def _infer_genre(media_type: str, title: str) -> str:
    type_genres = _GENRE_MAP.get(media_type, {})
    for genre, keywords in type_genres.items():
        for keyword in keywords:
            if keyword in title:
                return genre
    return "其他"


def _extract_notes_keywords(notes: str) -> list[str]:
    if not notes:
        return []
    stop_words = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
    words = []
    for char in ["，", "。", "！", "？", "、", "；", "：", "\n", " "]:
        notes = notes.replace(char, ",")
    for segment in notes.split(","):
        segment = segment.strip()
        if segment and len(segment) >= 2 and segment not in stop_words:
            words.append(segment)
    return words[:5]


def _rating_to_emotion(rating: float) -> str:
    for (low, high), emotion in _RATING_EMOTION_MAP.items():
        if low <= rating < high:
            return emotion
    return "中性"


def extract_media_signals(data: list[dict]) -> list[dict]:
    """提取媒体消费信号：题材偏好、主题关注、消费模式、情绪关联风格"""
    signals = []

    genre_counter: Counter = Counter()
    type_counter: Counter = Counter()
    rating_list: list[float] = []
    notes_keywords: list[str] = []
    monthly_counter: Counter = Counter()

    for item in data:
        title = item.get("title", "")
        media_type = item.get("type", "book")
        rating = item.get("rating", 0) or 0
        notes = item.get("notes", "")
        consumed_date = item.get("consumed_date", "")

        genre = _infer_genre(media_type, title)
        genre_counter[genre] += 1
        type_counter[media_type] += 1

        if rating > 0:
            rating_list.append(rating)
            emotion = _rating_to_emotion(rating)
        else:
            emotion = "中性"

        keywords = _extract_notes_keywords(notes)
        notes_keywords.extend(keywords)

        if consumed_date and len(consumed_date) >= 7:
            month_key = consumed_date[:7]
            monthly_counter[month_key] += 1

        signals.append({
            "timestamp": consumed_date or datetime.now().strftime("%Y-%m-%d"),
            "title": title,
            "media_type": media_type,
            "genre": genre,
            "rating": rating,
            "emotion": emotion,
            "notes_keywords": keywords,
        })

    if signals:
        top_genre = genre_counter.most_common(1)[0][0] if genre_counter else "其他"
        top_type = type_counter.most_common(1)[0][0] if type_counter else "book"
        avg_rating = sum(rating_list) / len(rating_list) if rating_list else 0
        keyword_counter = Counter(notes_keywords)
        top_keywords = [kw for kw, _ in keyword_counter.most_common(5)]

        signals.append({
            "timestamp": signals[0].get("timestamp", datetime.now().strftime("%Y-%m-%d")),
            "title": "媒体消费汇总",
            "media_type": top_type,
            "genre": top_genre,
            "rating": avg_rating,
            "emotion": _rating_to_emotion(avg_rating) if avg_rating > 0 else "中性",
            "notes_keywords": top_keywords,
            "summary": (
                f"媒体消费汇总：共 {len(data)} 条记录，"
                f"主要类型「{top_type}」，"
                f"偏好题材「{top_genre}」，"
                f"平均评分 {avg_rating:.1f}，"
                f"关注关键词：{'、'.join(top_keywords[:3])}"
            ),
        })

    return signals


async def _create_media_timeline_event(signal: dict, import_batch_id: str) -> None:
    """将媒体消费信号写入时间线事件"""
    event_id = uuid.uuid4().hex
    timestamp = signal.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    is_summary = signal.get("title") == "媒体消费汇总"
    if is_summary:
        summary = signal.get("summary", "媒体消费汇总")
        event_type = "media_summary"
        importance = 0.5
    else:
        title = signal.get("title", "")
        media_type = signal.get("media_type", "book")
        genre = signal.get("genre", "")
        rating = signal.get("rating", 0)
        emotion = signal.get("emotion", "")
        type_label = {"book": "读", "movie": "看", "tv_series": "追", "music": "听", "podcast": "听"}.get(media_type, "消费")
        summary = f"{type_label}了《{title}》评分{rating}（{genre}，{emotion}）"
        event_type = "media_consumption"
        importance = 0.4 if rating >= 4.5 else 0.3

    event = TimelineEventCreate(
        timestamp=timestamp,
        event_type=event_type,
        summary=summary,
        sentiment=None,
        emotional_keywords=signal.get("emotion", ""),
        related_contacts="",
        related_events="",
        source_type="media",
        source_id=f"media:{import_batch_id}:{event_id}",
        importance_score=importance,
        is_milestone=False,
    )

    await create_timeline_event(event)


async def import_media_records(
    data: list[dict],
    import_batch_id: str | None = None,
) -> dict:
    """
    导入书影音记录
    数据格式：[{title, type, consumed_date, rating, notes}]
    type: book|movie|tv_series|music|podcast
    """
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    signals = extract_media_signals(data)

    for signal in signals:
        await _create_media_timeline_event(signal, import_batch_id)

    logger.info(
        "书影音记录导入完成",
        import_batch_id=import_batch_id,
        imported_count=len(data),
    )

    asyncio.create_task(extract_knowledge_from_import(
        {"title": f"书影音记录 {datetime.now().strftime('%Y-%m')}", "type": "media", "summary": f"书影音消费记录，共 {len(data)} 条"},
        "media"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": len(data)}
