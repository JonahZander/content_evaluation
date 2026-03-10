"""URL extraction provider."""

from __future__ import annotations

import httpx
import trafilatura

from content_evaluation.domain.exceptions import ProviderError


class TrafilaturaExtractionProvider:
    """Extract readable text from a URL."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        """Initialize the extraction client."""

        self._timeout_seconds = timeout_seconds

    async def extract(self, url: str) -> dict[str, str]:
        """Fetch a URL and extract readable article text."""

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            raise ProviderError(f"Content extraction failed with status {response.status_code}")
        downloaded = response.text
        extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        if not extracted:
            raise ProviderError("Could not extract readable article content")
        return {"title": url, "text": extracted}
