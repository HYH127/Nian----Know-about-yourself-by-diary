import re
from typing import List

import jieba
import jieba.analyse

_MEDIA_PATTERNS = [
    re.compile(r"(?:看了|在看|看了个|刷了|追了|读了|在读|听了|在听|玩了|在玩)\s*《([^》]+)》"),
    re.compile(r"(?:电影|书|剧|番|动漫|游戏|音乐|播客)\s*[:：]?\s*《([^》]+)》"),
    re.compile(r"《([^》]+)》(?:这部电影|这本书|这部电视剧|这部番|这部动漫|这个游戏)"),
]

_WHITESPACE_RE = re.compile(r"\s+")
_SPECIAL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def extract_keywords(text: str, top_k: int = 10) -> List[str]:
    return jieba.analyse.extract_tags(text, topK=top_k)


def extract_topics(text: str, top_k: int = 5) -> List[str]:
    return jieba.analyse.textrank(text, topK=top_k)


def detect_media_mentions(text: str) -> List[str]:
    results: List[str] = []
    for pattern in _MEDIA_PATTERNS:
        matches = pattern.findall(text)
        results.extend(matches)
    return list(dict.fromkeys(results))


def clean_text(text: str) -> str:
    text = _SPECIAL_CHAR_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def split_long_text(content: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    """将长文本按段落 + 字符上限切分为多个片段，相邻片段保留 overlap 重叠。

    优先按段落（换行符）切分，若单段超过 chunk_size 则在段内按 chunk_size 硬切。
    相邻片段之间保留 overlap 个字符的重叠，保证语义连续性。
    """
    if not content or len(content) <= chunk_size:
        return [content] if content else []

    paragraphs = content.split("\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 单段过长则硬切
        if len(para) > chunk_size:
            if current:
                chunks.append(current)
                current = current[-overlap:] if len(current) > overlap else ""
            for i in range(0, len(para), chunk_size - overlap):
                piece = para[i : i + chunk_size]
                if len(piece) < 20:
                    break
                chunks.append(piece)
            continue
        # 累积到 chunk_size
        if len(current) + len(para) + 1 > chunk_size:
            chunks.append(current)
            current = current[-overlap:] + "\n" + para if len(current) > overlap else para
        else:
            current = current + "\n" + para if current else para

    if current:
        chunks.append(current)

    return chunks
