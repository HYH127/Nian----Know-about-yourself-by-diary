import asyncio
import hashlib
import os
import time

import structlog

logger = structlog.get_logger()

_model = None
_model_load_attempted = False  # 标记是否已尝试加载，避免每次请求都重试
_cache: dict[str, tuple[float, list[dict]]] = {}


def _load_model():
    """加载 bge-reranker 模型。

    优先级：
    1. 配置禁用 → 直接返回 None
    2. 本地路径 → 从本地加载
    3. HF 镜像 → 设置 HF_ENDPOINT 后下载

    加载失败后 _model_load_attempted 置 True，本次进程不再重试。
    """
    global _model, _model_load_attempted
    if _model is not None:
        return _model
    if _model_load_attempted:
        return None

    _model_load_attempted = True

    # 从环境变量读取配置（由 RerankerConfig 注入）
    enabled = os.environ.get("RERANKER_ENABLED", "true").lower() in ("true", "1", "yes")
    if not enabled:
        logger.info("reranker_disabled_by_config")
        return None

    model_name = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    hf_endpoint = os.environ.get("RERANKER_HF_ENDPOINT", "https://hf-mirror.com")

    # HF_HOME 和 HF_ENDPOINT 已在 config.py from_yaml() 中设置

    try:
        from FlagEmbedding import FlagReranker

        # HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE 已在 config.py 中根据缓存是否存在自动设置
        # HF_HOME / HF_ENDPOINT 也已设置
        logger.info("reranker_model_loading", model=model_name, offline=os.environ.get("HF_HUB_OFFLINE", "0"))
        _model = FlagReranker(model_name, use_fp16=True)
        logger.info("reranker_model_loaded", model=model_name)
        return _model
    except Exception as e:
        logger.warning("reranker_model_load_failed", model=model_name, error=str(e))
        return None


def _build_cache_key(query: str, candidates: list[dict]) -> str:
    # 兼容无 slug 的候选：使用 source_type + content hash 作为 fallback
    parts = []
    for c in candidates:
        slug = c.get("slug") or c.get("source_id") or c.get("id") or ""
        if slug:
            parts.append(slug)
        else:
            snippet = c.get("snippet", "") or c.get("content", "") or c.get("summary", "")
            parts.append(hashlib.md5(snippet.encode()).hexdigest()[:8])
    parts.sort()
    raw = f"{query}|{','.join(parts)}"
    return hashlib.md5(raw.encode()).hexdigest()


async def rerank(query: str, candidates: list[dict], top_n: int = 20) -> list[dict]:
    # Edge cases: empty candidates or empty query
    if not candidates:
        return []
    if not query:
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        for c in candidates:
            c["_rerank_score"] = c.get("score", 0)
        return candidates[:top_n]

    # Check MD5-based cache (TTL = 300s)
    key = _build_cache_key(query, candidates)
    if key in _cache:
        ts, results = _cache[key]
        if time.time() - ts < 300:
            return results

    # Try cross-encoder model
    model = _load_model()
    if model is not None:
        try:
            pairs = [[query, c.get("snippet", "")] for c in candidates]
            scores = await asyncio.to_thread(model.compute_score, pairs)
            if isinstance(scores, float):
                scores = [scores]
            for i, c in enumerate(candidates):
                c["_rerank_score"] = float(scores[i]) if i < len(scores) else 0.0
            candidates.sort(key=lambda x: x.get("_rerank_score", 0), reverse=True)
            result = candidates[:top_n]
            _cache[key] = (time.time(), result)
            return result
        except Exception:
            pass

    # Fallback: sort by existing "score" field
    candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
    for c in candidates:
        c["_rerank_score"] = c.get("score", 0)
    result = candidates[:top_n]
    _cache[key] = (time.time(), result)
    return result