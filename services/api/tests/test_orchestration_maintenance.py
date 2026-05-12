"""Focused regression tests for backend maintenance fixes."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from content_evaluation.domain.exceptions import NotFoundError, RunCancelledError
from content_evaluation.domain.models import (
    AnalysisArtifact,
    ArtifactSource,
    ContentFormat,
    OrchestratorBackend,
    RunConfig,
    RunInput,
    RunStatus,
    RuntimeMode,
    SourceType,
)
from content_evaluation.providers.mock.providers import (
    MockAnalysisProvider,
    MockContentExtractionProvider,
    MockDeepResearchProvider,
    MockSimilaritySearchProvider,
)
from content_evaluation.repositories.in_memory import InMemoryRunRepository
from content_evaluation.services.orchestration import RunOrchestrator


def _build_orchestrator(repository: object) -> RunOrchestrator:
    """Build a test orchestrator with mock providers."""

    return RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        agent_max_retries=2,
        deep_research_provider=MockDeepResearchProvider(),
    )


class StatusOnlyRepository:
    """Provide only the narrow run-status lookup used by cancellation checks."""

    def __init__(self, status: RunStatus) -> None:
        self.status = status
        self.status_calls = 0

    async def get_run_status(self, artifact_id: UUID) -> RunStatus:
        del artifact_id
        self.status_calls += 1
        return self.status

    async def get_artifact(self, artifact_id: UUID) -> AnalysisArtifact | None:
        raise AssertionError(f"full artifact lookup should not be used for {artifact_id}")


@pytest.mark.asyncio
async def test_preview_source_document_preserves_markdown_signals_in_manual_input() -> None:
    """Keep existing markdown-aware drafts rendered as markdown."""

    orchestrator = _build_orchestrator(InMemoryRunRepository())

    document = await orchestrator.preview_source_document(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            text="## Title\n\nThis paragraph uses **bold** text.",
        )
    )

    assert document.content_format is ContentFormat.MARKDOWN
    assert document.blocks[0].kind.value == "heading"
    assert document.blocks[0].text == "Title"
    assert any(mark.kind.value == "strong" for mark in document.blocks[1].marks)


@pytest.mark.asyncio
async def test_in_memory_repository_returns_run_status_without_loading_artifact() -> None:
    """Expose the narrow status lookup for orchestration hot paths."""

    repository = InMemoryRunRepository()
    artifact = AnalysisArtifact(
        source=ArtifactSource(source_type=SourceType.TEXT, source_label="draft"),
        run_config=RunConfig(selected_agents=["editorial"], runtime_mode=RuntimeMode.MOCK),
        status=RunStatus.CANCELED,
    )
    await repository.create_artifact(artifact)

    assert await repository.get_run_status(artifact.artifact_id) is RunStatus.CANCELED


@pytest.mark.asyncio
async def test_in_memory_repository_run_status_raises_for_missing_artifact() -> None:
    """Mirror the NotFound behavior used by the Postgres repository."""

    with pytest.raises(NotFoundError, match="Artifact"):
        await InMemoryRunRepository().get_run_status(uuid4())


@pytest.mark.asyncio
async def test_ensure_run_active_uses_status_lookup_only() -> None:
    """Check cancellation via the narrow repository API instead of a full artifact load."""

    repository = StatusOnlyRepository(RunStatus.CANCELED)
    orchestrator = _build_orchestrator(repository)

    with pytest.raises(RunCancelledError, match="Run stopped by user"):
        await orchestrator._ensure_run_active(uuid4())  # noqa: SLF001

    assert repository.status_calls == 1
