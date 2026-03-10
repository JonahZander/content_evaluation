"""Similarity search provider interfaces."""

from __future__ import annotations

from typing import Protocol


class SimilaritySearchProvider(Protocol):
    """Describe one provider that can search for related content."""

    async def search(self, query: str) -> list[dict[str, object]]:
        """Return similarity results for one query."""
