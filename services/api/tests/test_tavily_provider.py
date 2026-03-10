"""Tavily provider tests."""

import pytest
import respx
from httpx import Response

from content_evaluation.providers.tavily.client import TavilySearchProvider


@pytest.mark.asyncio
async def test_tavily_provider_serializes_results() -> None:
    """Return simplified Tavily results."""

    provider = TavilySearchProvider("key")
    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://api.tavily.com/search").mock(
            return_value=Response(200, json={"results": [{"title": "A", "url": "https://a.example", "score": 0.9}]})
        )
        results = await provider.search("query")

    assert route.called
    assert results == [{"title": "A", "url": "https://a.example", "score": 0.9}]
