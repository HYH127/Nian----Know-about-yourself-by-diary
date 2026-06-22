from __future__ import annotations

import json
import re

import structlog

from app.utils.llm import chat_completion

logger = structlog.get_logger()

MEDIA_PATTERNS = [
    r'(?:看了|读完|正在看|推荐|买了).{0,4}《([^》]+)》',
    r'《([^》]+)》.{0,4}(?:这本书|这本|看完|读完)',
    r'(?:看了|刷了|二刷|三刷).{0,4}《([^》]+)》',
    r'《([^》]+)》.{0,4}(?:这部电影|这片|看完|太好看了)',
    r'(?:追|在看|追完|追了).{0,4}《([^》]+)》',
    r'《([^》]+)》.{0,4}(?:这部剧|这剧|追完|更新)',
    r'(?:听了|单曲循环|推荐).{0,4}《([^》]+)》',
    r'(?:听了|推荐).{0,4}《([^》]+)》.{0,4}(?:播客|节目|电台)',
    r'(?:看了|读完|正在看|推荐|买了|最近看).{0,4}《([^》]+)》',
    r'《([^》]+)》.{0,4}(?:这本书|这本|看完|读完|真好看|怎么样)',
    r'(?:看了|追了|刷了|正在追|看过).{0,5}(?:一部|一个|那部).{0,3}(?:叫|叫做|名叫|名字叫)?(.{1,15}?)(?:的)?(?:电影|电视剧|剧|动漫|书|小说|漫画)',
    r'(?:像|跟|和).{0,5}(?:电影|电视剧|剧|动漫|书|小说|漫画)?[《「『](.+?)[》」』]\s*(?:里|里面|中)的',
    r'(?:像|跟|和).{0,3}(?:那个|哪个).{0,3}(?:叫|叫做).{0,3}(.{1,12}?)(?:的)?(?:下场|结局|一样|那样|那么)',
    r'.{0,3}(?:下场|结局|一样|那样|那么).{0,3}(?:电影|电视剧|剧|动漫|书)?.{0,3}[《「『](.+?)[》」』]',
    r'(?:看了|在看)(.+?)(?:电影|电视剧|剧|动漫|书|小说|漫画)',
]

_COMPILED_PATTERNS = [re.compile(p) for p in MEDIA_PATTERNS]


async def detect_media_mentions(text: str) -> list[dict]:
    """
    检测文本中提及的媒体作品
    规则 + LLM 双通道，LLM 始终执行（解决无书名号场景遗漏）
    返回: [{title, media_type, confidence, evidence}]
    """
    regex_results = _regex_detect(text)
    llm_results = await _llm_detect(text)
    return _merge_results(regex_results, llm_results)


def _regex_detect(text: str) -> list[dict]:
    """正则检测媒体提及"""
    results = []
    seen_titles = set()

    for pattern in _COMPILED_PATTERNS:
        matches = pattern.finditer(text)
        for match in matches:
            title = match.group(1)
            if title not in seen_titles:
                seen_titles.add(title)
                media_type = _infer_media_type(pattern.pattern, text, title)
                results.append({
                    "title": title,
                    "media_type": media_type,
                    "confidence": "explicit",
                    "evidence": match.group(0),
                })

    return results


async def _llm_detect(text: str) -> list[dict]:
    """LLM 检测媒体提及"""
    from app.prompts.media_detection import MEDIA_DETECTION_PROMPT

    response = await chat_completion(
        messages=[{"role": "user", "content": MEDIA_DETECTION_PROMPT.format(text=text)}],
        temperature=0.1,
        purpose="媒体检测",
    )
    try:
        results = json.loads(response)
        if isinstance(results, list):
            return results
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _merge_results(regex_results: list[dict], llm_results: list[dict]) -> list[dict]:
    """合并规则和 LLM 检测结果，去重"""
    seen_titles = set()
    merged = []

    for r in regex_results:
        key = r["title"]
        if key not in seen_titles:
            seen_titles.add(key)
            merged.append(r)

    for r in llm_results:
        key = r.get("title", "")
        if key and key not in seen_titles:
            seen_titles.add(key)
            merged.append(r)

    return merged


def _infer_media_type(pattern: str, text: str, title: str) -> str:
    """推断媒体类型"""
    if '书' in text or '读' in text:
        return 'book'
    elif '电影' in text or '片' in text or '刷' in text:
        return 'movie'
    elif '剧' in text or '追' in text:
        return 'tv_series'
    elif '歌' in text or '听' in text or '音乐' in text:
        return 'music'
    elif '播客' in text or '节目' in text:
        return 'podcast'
    return 'unknown'
