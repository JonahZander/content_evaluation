"""Extraction provider tests."""

from __future__ import annotations

import pytest

from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import ContentFormat, ExtractedContent
from content_evaluation.providers.extraction.client import FallbackExtractionProvider


class StubPrimaryExtractor:
    """Return a configured response or error."""

    def __init__(self, result: ExtractedContent | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def extract(self, url: str) -> ExtractedContent:
        del url
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class StubFallbackExtractor(StubPrimaryExtractor):
    """Use the same stub shape as the primary extractor."""


@pytest.mark.asyncio
async def test_fallback_extractor_returns_direct_result_without_tavily() -> None:
    """Keep the direct result when direct extraction succeeds."""

    primary = StubPrimaryExtractor(
        result=ExtractedContent(
            title="Direct",
            content="Article body",
            content_format=ContentFormat.PLAIN_TEXT,
            metadata={"provider_name": "direct"},
        )
    )
    fallback = StubFallbackExtractor(
        result=ExtractedContent(
            title="Fallback",
            content="Fallback body",
            content_format=ContentFormat.MARKDOWN,
            metadata={"provider_name": "tavily-extract"},
        )
    )

    extracted = await FallbackExtractionProvider(primary, fallback).extract("https://example.com")

    assert extracted.title == "Direct"
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_fallback_extractor_uses_tavily_on_403() -> None:
    """Fall back to Tavily when direct extraction is blocked."""

    primary = StubPrimaryExtractor(error=ProviderError("Direct content extraction failed with status 403"))
    fallback = StubFallbackExtractor(
        result=ExtractedContent(
            title="Fallback",
            content="## Markdown",
            content_format=ContentFormat.MARKDOWN,
            metadata={"provider_name": "tavily-extract"},
        )
    )

    extracted = await FallbackExtractionProvider(primary, fallback).extract("https://example.com")

    assert extracted.content_format == ContentFormat.MARKDOWN
    assert extracted.metadata["fallback_used"] is True
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_fallback_extractor_uses_tavily_when_direct_extracts_no_text() -> None:
    """Fall back when direct extraction returns no readable article text."""

    primary = StubPrimaryExtractor(error=ProviderError("Direct content extraction returned no readable article text"))
    fallback = StubFallbackExtractor(
        result=ExtractedContent(
            title="Fallback",
            content="Recovered body",
            content_format=ContentFormat.MARKDOWN,
            metadata={"provider_name": "tavily-extract"},
        )
    )

    extracted = await FallbackExtractionProvider(primary, fallback).extract("https://example.com")

    assert extracted.title == "Fallback"
    assert extracted.metadata["fallback_used"] is True


@pytest.mark.asyncio
async def test_fallback_extractor_reports_both_failures() -> None:
    """Return a clear error when the primary and fallback both fail."""

    primary = StubPrimaryExtractor(error=ProviderError("Direct content extraction failed with status 403"))
    fallback = StubFallbackExtractor(error=ProviderError("Tavily extraction failed with status 500"))

    with pytest.raises(ProviderError, match="Tavily fallback failed"):
        await FallbackExtractionProvider(primary, fallback).extract("https://example.com")
