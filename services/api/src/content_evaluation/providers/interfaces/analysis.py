"""Analysis provider interfaces."""

from __future__ import annotations

from typing import Protocol

from content_evaluation.domain.models import ArtifactBlock, ProviderRoute, RevisionMode


class AnalysisProvider(Protocol):
    """Describe one provider that can produce structured agent results."""

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        """Return one structured JSON object for an agent run."""

    async def generate_revised_markdown(
        self,
        original_markdown: str,
        accepted_suggestions: list[dict[str, object]],
        mode: RevisionMode,
        direction_prompt: str | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        """Return one revised-markdown payload built from accepted suggestions."""

    def resolve_model_name(self, route: ProviderRoute | None = None) -> str:
        """Return the resolved model name for one analysis run."""
