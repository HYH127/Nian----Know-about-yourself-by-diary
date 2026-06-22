from __future__ import annotations

import re
import json
from app.config import settings
from app.utils.llm import chat_completion


INTENT_PATTERNS = {
    "emotion": [
        r"焦虑|难过|孤独|压力|伤心|害怕|恐惧",
        r"开心|快乐|兴奋|幸福|满足|放松",
        r"烦躁|担心|不安|痛苦|失落|迷茫|沮丧",
        r"心情|情绪|感受|心里|难受|压抑",
    ],
    "decision": [
        r"要不要|该不该|选哪个|怎么办",
        r"如何选择|怎么决定|建议|推荐",
        r"纠结|犹豫|取舍|抉择|方案",
    ],
    "knowledge": [
        r"什么是|定义|概念|原理|为什么",
        r"如何|怎么|教程|指南|方法",
        r"学习|理解|解释|介绍|说明",
    ],
    "relationship": [
        r"谁|认识|朋友|同学|老师|家人",
        r"关系|社交|交往|互动|联系",
        r"沟通|相处|吵架|和好|矛盾",
    ],
    "event": [
        r"什么时候|哪一天|发生|经过|结果",
        r"那天|那天|记得|回忆|当时",
        r"事件|事情|经历|过程|细节",
    ],
}

REWRITE_TEMPLATES = {
    "emotion": ["情绪", "感受", "原因"],
    "decision": ["选择", "决定", "利弊", "方案"],
    "knowledge": ["概念", "原理", "定义", "解释"],
    "relationship": ["关系", "社交", "互动"],
    "event": ["事件", "经过", "结果"],
}


def detect_intent(query: str) -> str:
    scores = {}
    for intent, patterns in INTENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            matches = re.findall(pattern, query)
            score += len(matches)
        if score > 0:
            scores[intent] = score
    if not scores:
        return "knowledge"
    return max(scores, key=scores.get)


def rewrite_basic(query: str, intent: str) -> str:
    stop_words = {
        "的", "了", "是", "我", "在", "不", "也", "就", "都", "很",
        "吗", "呢", "啊", "吧", "呀", "哦", "哈", "嘛",
        "你", "他", "她", "它", "们", "这", "那",
        "什么", "怎么", "为什么", "如何",
    }

    terms = []
    for token in re.findall(r"[\u4e00-\u9fff]{1,6}|[a-zA-Z]{2,}", query):
        if token not in stop_words:
            terms.append(token)

    expansions = REWRITE_TEMPLATES.get(intent, [])
    expanded = terms + expansions

    return " ".join(expanded[:12])


async def rewrite_llm(query: str, intent: str) -> str:
    try:
        rewritten = await chat_completion(
            model=settings.llm.chat_mini_model,
            messages=[{
                "role": "user",
                "content": (
                    "将以下查询改写为更适合信息检索的关键词组合，保留核心意图。"
                    "只输出关键词，不要解释。\n\n"
                    f"查询：{query}\n"
                    f"意图类型：{intent}"
                ),
            }],
            temperature=0.1,
            max_tokens=80,
            purpose="查询改写",
        )
        return rewritten.strip() if rewritten else rewrite_basic(query, intent)
    except Exception:
        return rewrite_basic(query, intent)


async def rewrite_query(query: str, mode: str = "balanced") -> tuple[str, str]:
    if mode == "conservative":
        return query, "none"

    intent = detect_intent(query)

    if mode == "tokenmax":
        rewritten = await rewrite_llm(query, intent)
    else:
        rewritten = rewrite_basic(query, intent)

    return rewritten, intent