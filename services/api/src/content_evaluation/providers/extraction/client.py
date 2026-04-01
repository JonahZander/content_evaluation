"""URL extraction providers."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import ContentFormat, ExtractedContent

_ALLOWED_SCHEMES = {"http", "https"}


async def _validate_url(url: str) -> None:
    """Reject URLs with non-public schemes or that resolve to private/internal IPs."""

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ProviderError(f"Disallowed URL scheme: {parsed.scheme!r}")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ProviderError("URL has no hostname")
    try:
        results = await asyncio.to_thread(
            socket.getaddrinfo, hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ProviderError(f"Could not resolve hostname {hostname!r}") from exc
    for *_, sockaddr in results:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ProviderError(f"Disallowed URL: resolves to non-public IP {ip}")


class TrafilaturaExtractionProvider:
    """Extract readable markdown from a URL with direct fetch + trafilatura."""

    provider_name = "direct"

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        """Initialize the extraction client with a long-lived HTTP session."""

        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    async def extract(self, url: str) -> ExtractedContent:
        """Fetch a URL and extract readable article markdown."""

        await _validate_url(url)
        response = await self._client.get(url)
        if response.status_code >= 400:
            raise ProviderError(f"Direct content extraction failed with status {response.status_code}")

        downloaded = response.text
        extracted = trafilatura.extract(
            downloaded,
            output_format="markdown",
            include_comments=False,
            include_tables=False,
            include_links=True,
        )
        if not extracted:
            raise ProviderError("Direct content extraction returned no readable article text")

        return ExtractedContent(
            title=url,
            content=extracted,
            content_format=ContentFormat.MARKDOWN,
            metadata={
                "provider_name": self.provider_name,
                "content_format": ContentFormat.MARKDOWN.value,
                "source_url": url,
            },
        )


class TavilyExtractionProvider:
    """Extract markdown article content through Tavily."""

    provider_name = "tavily-extract"

    def __init__(self, api_key: str, *, timeout_seconds: float = 20.0) -> None:
        """Initialize the Tavily extraction client with a long-lived HTTP session."""

        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    async def extract(self, url: str) -> ExtractedContent:
        """Request markdown content for one URL from Tavily."""

        await _validate_url(url)
        response = await self._client.post(
            "https://api.tavily.com/extract",
            json={
                "api_key": self._api_key,
                "urls": [url],
                "extract_depth": "advanced",
                "format": "markdown",
                "include_images": False,
            },
        )
        if response.status_code >= 400:
            raise ProviderError(f"Tavily extraction failed with status {response.status_code}")

        payload = response.json()
        results = payload.get("results", [])
        if not isinstance(results, list) or not results:
            raise ProviderError("Tavily extraction returned no results")

        item = results[0]
        if not isinstance(item, dict):
            raise ProviderError("Tavily extraction returned an invalid payload")

        raw_content = item.get("raw_content")
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise ProviderError("Tavily extraction returned no readable article content")

        item_title = item.get("title")
        title = item_title if isinstance(item_title, str) and item_title else url
        return ExtractedContent(
            title=title,
            content=raw_content.strip(),
            content_format=ContentFormat.MARKDOWN,
            metadata={
                "provider_name": self.provider_name,
                "content_format": ContentFormat.MARKDOWN.value,
                "source_url": item.get("url", url),
                "images_included": False,
            },
        )


class FallbackExtractionProvider:
    """Try direct extraction first and fall back to Tavily when needed."""

    def __init__(
        self,
        primary: TrafilaturaExtractionProvider,
        fallback: TavilyExtractionProvider,
    ) -> None:
        """Initialize the fallback extraction chain."""

        self._primary = primary
        self._fallback = fallback

    async def close(self) -> None:
        """Close both underlying providers."""

        await self._primary.close()
        await self._fallback.close()

    async def extract(self, url: str) -> ExtractedContent:
        """Extract content via direct fetch, then Tavily if needed."""

        try:
            return await self._primary.extract(url)
        except ProviderError as primary_error:
            if not _should_try_fallback(str(primary_error)):
                raise ProviderError(f"Content extraction failed: {primary_error}") from primary_error

            try:
                extracted = await self._fallback.extract(url)
            except ProviderError as fallback_error:
                raise ProviderError(
                    f"Content extraction failed: {primary_error}; Tavily fallback failed: {fallback_error}"
                ) from fallback_error

            extracted.metadata["fallback_used"] = True
            extracted.metadata["primary_error"] = str(primary_error)
            return extracted


def _should_try_fallback(message: str) -> bool:
    """Return whether a direct extraction error should trigger fallback."""

    status_codes = (
        "status 403",
        "status 429",
        "status 500",
        "status 502",
        "status 503",
        "status 504",
    )
    return (
        any(status in message for status in status_codes)
        or "no readable article text" in message
    )
