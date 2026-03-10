"""Analysis provider interfaces."""

from __future__ import annotations

from typing import Protocol

from content_evaluation.domain.models import AgentCategory, DocumentBlock


class AnalysisProvider(Protocol):
    """Describe one provider that can produce structured findings."""

    async def analyze_category(
        self,
        category: AgentCategory,
        title: str,
        blocks: list[DocumentBlock],
    ) -> list[dict[str, object]]:
        """Return structured findings for one analysis category."""
