"""Content extraction provider interfaces."""

from __future__ import annotations

from typing import Protocol

from content_evaluation.domain.models import ExtractedContent


class ContentExtractionProvider(Protocol):
    """Describe one provider that can extract readable article content."""

    async def extract(self, url: str) -> ExtractedContent:
        """Return extracted source content for one URL."""
