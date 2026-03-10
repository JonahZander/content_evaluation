"""Content extraction provider interfaces."""

from __future__ import annotations

from typing import Protocol


class ContentExtractionProvider(Protocol):
    """Describe one provider that can extract readable article content."""

    async def extract(self, url: str) -> dict[str, str]:
        """Return a title and normalized text for one URL."""
