"""Extraction provider tests using respx to mock httpx requests.

Tests cover TrafilaturaExtractionProvider and TavilyExtractionProvider
individually, including success paths, HTTP errors, empty results,
and SSRF rejection.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import respx
from httpx import Response

from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import ContentFormat
from content_evaluation.providers.extraction.client import (
    TavilyExtractionProvider,
    TrafilaturaExtractionProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE_URL = "https://example.com/article"


def _patch_validate_url():
    """Skip DNS-based SSRF validation so respx-mocked URLs work."""

    async def _noop(url: str) -> None:
        pass

    return patch("content_evaluation.providers.extraction.client._validate_url", _noop)


# ---------------------------------------------------------------------------
# TrafilaturaExtractionProvider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trafilatura_successful_extraction() -> None:
    provider = TrafilaturaExtractionProvider(timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.get(_SAFE_URL).mock(return_value=Response(200, text="<html><body><p>Article body text.</p></body></html>"))

            with patch("content_evaluation.providers.extraction.client.trafilatura.extract", return_value="Article body text."):
                result = await provider.extract(_SAFE_URL)

        assert result.content == "Article body text."
        assert result.content_format is ContentFormat.PLAIN_TEXT
        assert result.metadata["provider_name"] == "direct"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_trafilatura_http_error() -> None:
    provider = TrafilaturaExtractionProvider(timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.get(_SAFE_URL).mock(return_value=Response(403))

            with pytest.raises(ProviderError, match="status 403"):
                await provider.extract(_SAFE_URL)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_trafilatura_empty_extraction() -> None:
    provider = TrafilaturaExtractionProvider(timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.get(_SAFE_URL).mock(return_value=Response(200, text="<html></html>"))

            with patch("content_evaluation.providers.extraction.client.trafilatura.extract", return_value=None):
                with pytest.raises(ProviderError, match="no readable article text"):
                    await provider.extract(_SAFE_URL)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_trafilatura_ssrf_rejection_private_ip() -> None:
    """Reject URLs that resolve to private IPs."""

    provider = TrafilaturaExtractionProvider(timeout_seconds=5.0)
    try:
        with pytest.raises(ProviderError, match="non-public IP|Disallowed URL"):
            await provider.extract("http://127.0.0.1/secret")
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_trafilatura_ssrf_rejection_non_http_scheme() -> None:
    """Reject non-HTTP/HTTPS schemes."""

    provider = TrafilaturaExtractionProvider(timeout_seconds=5.0)
    try:
        with pytest.raises(ProviderError, match="Disallowed URL scheme"):
            await provider.extract("ftp://example.com/file")
    finally:
        await provider.close()


# ---------------------------------------------------------------------------
# TavilyExtractionProvider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_extraction_successful() -> None:
    provider = TavilyExtractionProvider("key", timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.post("https://api.tavily.com/extract").mock(
                return_value=Response(
                    200,
                    json={
                        "results": [
                            {
                                "title": "Article Title",
                                "url": _SAFE_URL,
                                "raw_content": "## Markdown Content\n\nBody text.",
                            }
                        ]
                    },
                )
            )
            result = await provider.extract(_SAFE_URL)

        assert result.title == "Article Title"
        assert result.content_format is ContentFormat.MARKDOWN
        assert "Body text" in result.content
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_tavily_extraction_http_error() -> None:
    provider = TavilyExtractionProvider("key", timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.post("https://api.tavily.com/extract").mock(return_value=Response(500))

            with pytest.raises(ProviderError, match="status 500"):
                await provider.extract(_SAFE_URL)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_tavily_extraction_empty_results() -> None:
    provider = TavilyExtractionProvider("key", timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.post("https://api.tavily.com/extract").mock(
                return_value=Response(200, json={"results": []})
            )

            with pytest.raises(ProviderError, match="no results"):
                await provider.extract(_SAFE_URL)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_tavily_extraction_malformed_result() -> None:
    provider = TavilyExtractionProvider("key", timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.post("https://api.tavily.com/extract").mock(
                return_value=Response(200, json={"results": ["not a dict"]})
            )

            with pytest.raises(ProviderError, match="invalid payload"):
                await provider.extract(_SAFE_URL)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_tavily_extraction_empty_content() -> None:
    provider = TavilyExtractionProvider("key", timeout_seconds=5.0)
    try:
        with _patch_validate_url(), respx.mock(assert_all_called=True) as router:
            router.post("https://api.tavily.com/extract").mock(
                return_value=Response(200, json={"results": [{"title": "A", "url": _SAFE_URL, "raw_content": "  "}]})
            )

            with pytest.raises(ProviderError, match="no readable article content"):
                await provider.extract(_SAFE_URL)
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_tavily_extraction_ssrf_rejection() -> None:
    provider = TavilyExtractionProvider("key", timeout_seconds=5.0)
    try:
        with pytest.raises(ProviderError, match="Disallowed URL scheme"):
            await provider.extract("ftp://evil.example/data")
    finally:
        await provider.close()
