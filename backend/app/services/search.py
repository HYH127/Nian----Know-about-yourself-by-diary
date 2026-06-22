from __future__ import annotations

import asyncio
import time

from tavily import TavilyClient

from app.config import settings


class SearchService:
    def __init__(self):
        self._client = None
        self._cache = {}
        self._cache_timestamps = {}

    @property
    def client(self) -> TavilyClient:
        if self._client is None:
            self._client = TavilyClient(api_key=settings.tavily.api_key)
        return self._client

    async def search(
        self,
        query: str,
        search_depth: str = None,
        max_results: int = None,
    ) -> list[dict]:
        """
        联网搜索（受 include_domains 限制，用于媒体检测等内部场景）
        返回: [{title, url, content, score}]
        """
        cache_key = f"restricted:{query.lower().strip()}"
        if cache_key in self._cache:
            cached_time = self._cache_timestamps.get(cache_key, 0)
            if time.time() - cached_time < settings.tavily.cache_ttl_hours * 3600:
                return self._cache[cache_key]

        depth = search_depth or settings.tavily.search_depth
        max_res = max_results or settings.tavily.max_results_per_query

        result = await asyncio.to_thread(
            self.client.search,
            query=query,
            search_depth=depth,
            max_results=max_res,
            include_domains=settings.tavily.include_domains or None,
        )

        results = []
        for item in result.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0),
            })

        self._cache[cache_key] = results
        self._cache_timestamps[cache_key] = time.time()

        return results

    async def search_unrestricted(
        self,
        query: str,
        search_depth: str = "advanced",
        max_results: int = 5,
    ) -> list[dict]:
        """
        无域名限制的联网搜索（用于对话中用户主动搜索场景）
        不限制来源网站，以搜到用户关心的内容为主。
        返回: [{title, url, content, score}]
        """
        cache_key = f"unrestricted:{query.lower().strip()}"
        if cache_key in self._cache:
            cached_time = self._cache_timestamps.get(cache_key, 0)
            if time.time() - cached_time < settings.tavily.cache_ttl_hours * 3600:
                return self._cache[cache_key]

        result = await asyncio.to_thread(
            self.client.search,
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_domains=[],  # 不限制域名
        )

        results = []
        for item in result.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0),
            })

        self._cache[cache_key] = results
        self._cache_timestamps[cache_key] = time.time()

        return results

    async def multi_search(self, queries: list[str]) -> dict[str, list[dict]]:
        """多查询并行搜索"""
        tasks = [self.search(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            q: r if not isinstance(r, Exception) else []
            for q, r in zip(queries, results)
        }


search_service = SearchService()
