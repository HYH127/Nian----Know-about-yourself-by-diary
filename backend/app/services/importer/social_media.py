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

_EMOTION_KEYWORDS_MAP = {
    "开心": ["哈哈", "开心", "快乐", "幸福", "太好了", "棒", "喜欢", "爱", "美好"],
    "愤怒": ["气死", "愤怒", "无语", "烦", "讨厌", "受不了", "可恶"],
    "悲伤": ["难过", "伤心", "失望", "遗憾", "心痛", "哭", "泪"],
    "焦虑": ["焦虑", "担心", "害怕", "紧张", "不安", "压力"],
    "平静": ["平静", "还好", "一般", "日常", "普通"],
}

_TOPIC_KEYWORDS_MAP = {
    "工作": ["工作", "上班", "加班", "项目", "会议", "领导", "同事"],
    "生活": ["生活", "日常", "做饭", "家务", "散步", "周末"],
    "情感": ["恋爱", "分手", "表白", "暗恋", "吵架", "复合"],
    "兴趣": ["追剧", "游戏", "读书", "运动", "旅行", "摄影"],
    "社会": ["新闻", "热点", "社会", "政策", "经济"],
}


def _detect_emotion(content: str) -> str:
    for emotion, keywords in _EMOTION_KEYWORDS_MAP.items():
        for keyword in keywords:
            if keyword in content:
                return emotion
    return "平静"


def _detect_topics(content: str) -> list[str]:
    topics = []
    for topic, keywords in _TOPIC_KEYWORDS_MAP.items():
        for keyword in keywords:
            if keyword in content:
                topics.append(topic)
                break
    return topics if topics else ["生活"]


def _compute_activity_level(likes: int, comments: int, shares: int) -> str:
    total = likes + comments + shares
    if total >= 100:
        return "高"
    elif total >= 20:
        return "中"
    return "低"


def extract_social_signals(data: list[dict], platform: str) -> list[dict]:
    """提取社交信号：公开展示面、活跃度、情绪表达风格、关注话题"""
    signals = []

    emotion_counter: Counter = Counter()
    topic_counter: Counter = Counter()
    activity_levels: list[str] = []
    hourly_counter: Counter = Counter()

    for item in data:
        content = item.get("content", "")
        emotion = _detect_emotion(content)
        topics = _detect_topics(content)
        likes = item.get("likes", 0) or 0
        comments = item.get("comments", 0) or 0
        shares = item.get("shares", 0) or 0
        activity = _compute_activity_level(likes, comments, shares)

        emotion_counter[emotion] += 1
        for topic in topics:
            topic_counter[topic] += 1
        activity_levels.append(activity)

        ts = item.get("timestamp", "")
        if ts and len(ts) >= 13:
            try:
                hour = int(ts[11:13])
                hourly_counter[hour] += 1
            except (ValueError, IndexError):
                pass

        signals.append({
            "timestamp": item.get("timestamp", ""),
            "platform": platform,
            "emotion": emotion,
            "topics": topics,
            "activity_level": activity,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "content_preview": content[:100] if content else "",
        })

    dominant_emotion = emotion_counter.most_common(1)[0][0] if emotion_counter else "平静"
    dominant_topic = topic_counter.most_common(1)[0][0] if topic_counter else "生活"
    high_activity_ratio = activity_levels.count("高") / len(activity_levels) if activity_levels else 0

    if signals:
        signals.append({
            "timestamp": signals[0].get("timestamp", ""),
            "platform": platform,
            "emotion": dominant_emotion,
            "topics": [dominant_topic],
            "activity_level": "汇总",
            "summary": (
                f"社交汇总：{platform} 共 {len(data)} 条帖子，"
                f"主要情绪「{dominant_emotion}」，"
                f"关注话题「{dominant_topic}」，"
                f"高活跃度占比 {high_activity_ratio:.0%}"
            ),
        })

    return signals


async def _create_social_timeline_event(signal: dict, import_batch_id: str) -> None:
    """将社交信号写入时间线事件"""
    event_id = uuid.uuid4().hex
    timestamp = signal.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    is_summary = signal.get("activity_level") == "汇总"
    if is_summary:
        summary = signal.get("summary", "社交数据汇总")
        event_type = "social_summary"
        importance = 0.5
    else:
        platform = signal.get("platform", "unknown")
        preview = signal.get("content_preview", "")
        emotion = signal.get("emotion", "")
        topics = signal.get("topics", [])
        summary = f"社交动态（{platform}）：{preview}（情绪：{emotion}，话题：{'/'.join(topics)}）"
        event_type = "social_post"
        importance = 0.3

    event = TimelineEventCreate(
        timestamp=timestamp,
        event_type=event_type,
        summary=summary,
        sentiment=None,
        emotional_keywords=signal.get("emotion", ""),
        related_contacts="",
        related_events="",
        source_type="social_media",
        source_id=f"{signal.get('platform', 'unknown')}:{import_batch_id}:{event_id}",
        importance_score=importance,
        is_milestone=False,
    )

    await create_timeline_event(event)


async def import_social_media(
    data: list[dict],
    platform: str,
    import_batch_id: str | None = None,
) -> dict:
    """
    导入社交媒体帖子
    数据格式：[{platform, timestamp, content, likes, comments, shares}]
    """
    if not import_batch_id:
        import_batch_id = uuid.uuid4().hex

    signals = extract_social_signals(data, platform)

    for signal in signals:
        await _create_social_timeline_event(signal, import_batch_id)

    logger.info(
        "社交媒体数据导入完成",
        import_batch_id=import_batch_id,
        platform=platform,
        imported_count=len(data),
    )

    asyncio.create_task(extract_knowledge_from_import(
        {"title": f"社交媒体数据 {platform}", "type": "social", "summary": f"社交媒体 {platform} 数据，共 {len(data)} 条帖子"},
        "social_media"
    ))

    return {"import_batch_id": import_batch_id, "imported_count": len(data)}
