"""Analysis provider interfaces."""

from __future__ import annotations

from typing import Protocol

from content_evaluation.domain.models import ArtifactBlock


class AnalysisProvider(Protocol):
    """Describe one provider that can produce structured agent results."""

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Return one structured JSON object for an agent run."""
