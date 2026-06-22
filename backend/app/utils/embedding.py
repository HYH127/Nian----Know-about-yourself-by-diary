from __future__ import annotations

from openai import AsyncOpenAI
from tenacity import retry, wait_exponential, stop_after_attempt

from app.config import settings

_client: AsyncOpenAI | None = None

_BATCH_SIZE = 10


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.llm.embedding_base_url,
            api_key=settings.llm.embedding_api_key,
        )
    return _client


@retry(
    wait=wait_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
)
async def embed_text(text: str) -> list[float]:
    client = _get_client()
    response = await client.embeddings.create(
        model=settings.llm.embedding_model,
        input=text,
        dimensions=settings.llm.embedding_dimensions,
    )
    return response.data[0].embedding


async def embed_texts(texts: list[str]) -> list[list[float]]:
    results: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        batch_results = await _embed_batch(batch)
        results.extend(batch_results)
    return results


@retry(
    wait=wait_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
)
async def _embed_batch(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    response = await client.embeddings.create(
        model=settings.llm.embedding_model,
        input=texts,
        dimensions=settings.llm.embedding_dimensions,
    )
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]
