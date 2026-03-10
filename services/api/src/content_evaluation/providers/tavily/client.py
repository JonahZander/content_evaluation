"""Tavily similarity search client."""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from content_evaluation.domain.exceptions import ProviderError


class TavilySearchProvider:
    """Call Tavily for related-content search."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 20.0) -> None:
        """Initialize the Tavily client."""

        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=5),
        retry=retry_if_exception_type((httpx.HTTPError, ProviderError)),
        reraise=True,
    )
    async def search(self, query: str) -> list[dict[str, object]]:
        """Search the Tavily API for related pages."""

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": 5,
                    "search_depth": "advanced",
                },
            )
        if response.status_code >= 400:
            raise ProviderError(f"Tavily request failed with status {response.status_code}")
        payload = response.json()
        results = payload.get("results", [])
        return [
            {
                "title": item.get("title", "Untitled"),
                "url": item.get("url", ""),
                "score": float(item.get("score", 0.0)),
            }
            for item in results
        ]
