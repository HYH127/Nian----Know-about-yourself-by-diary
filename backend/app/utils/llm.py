from typing import AsyncIterator
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from tenacity import retry, wait_exponential, stop_after_attempt

from app.config import settings

_client: AsyncOpenAI | None = None

# Context variable for tracking token usage within a diary processing session
_token_counter: ContextVar[int] = ContextVar("token_counter", default=0)

# LLM call log file
_LLM_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "llm_calls.log"

# ============================================================
# 工具定义：模型可调用的工具
# 参考：https://tianpan.co/zh/blog/2026-04-20-temporal-context-injection-llm
# 对于长时运行的会话，暴露一个时钟工具供智能体调用，
# 而不是依赖会话开始时注入的过期时间戳。
# ============================================================

LLM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "获取当前日期和时间。当你需要知道今天是几号、当前时间、星期几、或进行时间相关的推理时调用此工具。对于跨越午夜的会话尤其重要，因为系统提示中注入的日期可能已经过期。",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA 时区标识符，如 'Asia/Shanghai'、'America/New_York'、'UTC'。默认为 'Asia/Shanghai'。",
                        "default": "Asia/Shanghai",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索工具。当你需要查找实时信息、最新新闻、具体事实、人物/事件/地点的背景资料、书影音作品信息、技术问题解答等用户可能关心的内容时调用此工具。搜索结果不限制来源网站，以找到最相关内容为主。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询关键词，尽量具体明确。例如：'2026年世界杯举办地'、'《三体》小说简介'、'Python asyncio 最佳实践'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


async def execute_tool(tool_name: str, tool_args: dict) -> str:
    """执行工具调用并返回结果字符串。

    Args:
        tool_name: 工具名称
        tool_args: 工具参数

    Returns:
        工具执行结果（JSON 字符串）
    """
    import json as _json

    if tool_name == "get_current_date":
        tz_name = tool_args.get("timezone", "Asia/Shanghai")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
            tz_name = "UTC"

        now = datetime.now(tz)
        result = {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "timezone": tz_name,
            "iso8601": now.isoformat(),
        }
        return _json.dumps(result, ensure_ascii=False)

    elif tool_name == "web_search":
        query = tool_args.get("query", "").strip()
        if not query:
            return _json.dumps({"error": "搜索关键词不能为空"}, ensure_ascii=False)
        try:
            from app.services.search import search_service
            results = await search_service.search_unrestricted(query)
            return _json.dumps({
                "query": query,
                "results": results,
                "result_count": len(results),
            }, ensure_ascii=False)
        except Exception as e:
            return _json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)

    else:
        return _json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)


def get_date_prefix() -> str:
    """生成日期注入前缀，用于系统提示开头。

    按文章建议：ISO 8601 格式、以 UTC 为基准的日期，放在系统提示开头。
    只注入日期不注入时间，保证 24 小时内缓存稳定。
    """
    utc_date = datetime.now(timezone.utc).date().isoformat()
    return f"Today's date is {utc_date} UTC.\n"


def reset_token_counter() -> None:
    """Reset the token counter for a new processing session."""
    _token_counter.set(0)


def get_token_count() -> int:
    """Get the current accumulated token count."""
    return _token_counter.get()


def get_llm_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.llm.base_url,
            api_key=settings.llm.api_key,
        )
    return _client


def _log_llm_call(purpose: str, duration_s: float, tokens: int | None, model: str) -> None:
    """Append a single LLM call record to the log file."""
    try:
        _LLM_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        token_str = str(tokens) if tokens is not None else "N/A"
        with open(_LLM_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] 用途={purpose} | 耗时={duration_s:.2f}s | tokens={token_str} | 模型={model}\n")
    except Exception:
        pass


@retry(
    wait=wait_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
)
async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    purpose: str = "",
    **kwargs,
) -> str:
    """Call LLM chat completion with automatic logging.

    Args:
        purpose: Description of what this LLM call is for (e.g. "日记摘要", "实体编译").
    """
    import asyncio
    import structlog
    logger = structlog.get_logger()

    client = get_llm_client()
    use_model = model or settings.llm.chat_model
    start = asyncio.get_event_loop().time()
    total_tokens = None

    try:
        response = await client.chat.completions.create(
            model=use_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.llm.temperature,
            max_tokens=max_tokens or settings.llm.max_tokens,
            **kwargs,
        )
        # Accumulate token usage
        if response.usage and response.usage.total_tokens:
            total_tokens = response.usage.total_tokens
            try:
                current = _token_counter.get()
                _token_counter.set(current + total_tokens)
            except Exception:
                pass
        return response.choices[0].message.content or ""
    finally:
        elapsed = asyncio.get_event_loop().time() - start
        _log_llm_call(purpose or "未指定", elapsed, total_tokens, use_model)
        logger.debug("llm_call", purpose=purpose, elapsed=f"{elapsed:.2f}s", tokens=total_tokens, model=use_model)


@retry(
    wait=wait_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
)
async def stream_chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    purpose: str = "",
    **kwargs,
) -> AsyncIterator[str]:
    """Call LLM streaming chat completion with automatic logging."""
    import asyncio

    client = get_llm_client()
    use_model = model or settings.llm.chat_model
    start = asyncio.get_event_loop().time()
    total_tokens = None

    stream = await client.chat.completions.create(
        model=use_model,
        messages=messages,
        temperature=temperature if temperature is not None else settings.llm.temperature,
        max_tokens=max_tokens or settings.llm.max_tokens,
        stream=True,
        **kwargs,
    )
    collected = []
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            collected.append(delta.content)
            yield delta.content
        # Try to get usage from the last chunk
        if hasattr(chunk, 'usage') and chunk.usage:
            total_tokens = chunk.usage.total_tokens

    elapsed = asyncio.get_event_loop().time() - start
    _log_llm_call(purpose or "未指定(流式)", elapsed, total_tokens, use_model)
