"""LangGraph runtime tests."""

from __future__ import annotations

import pytest

from content_evaluation.domain.models import (
    GraphCheckpoint,
    GraphRunState,
    OrchestratorBackend,
    RunInput,
    RuntimeMode,
    SourceType,
)
from content_evaluation.providers.mock.providers import (
    MockAnalysisProvider,
    MockContentExtractionProvider,
    MockSimilaritySearchProvider,
)
from content_evaluation.repositories.in_memory import InMemoryRunRepository
from content_evaluation.services.orchestration import RunOrchestrator


@pytest.mark.asyncio
async def test_langgraph_run_completes_and_clears_checkpoint() -> None:
    """Process one run through LangGraph and clear the checkpoint on completion."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
    )
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
        )
    )

    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
        ),
    )

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.status.value == "completed"
    assert await repository.get_graph_checkpoint(artifact.artifact_id) is None


@pytest.mark.asyncio
async def test_langgraph_resume_uses_existing_checkpoint() -> None:
    """Resume a run from an existing graph checkpoint."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
    )
    input_data = RunInput(
        source_type=SourceType.TEXT,
        source_label="Draft",
        title="Draft",
        text="Alpha paragraph.\n\nBeta paragraph.",
    )
    artifact = await orchestrator.create_run(input_data)
    await repository.save_graph_checkpoint(
        GraphCheckpoint(
            artifact_id=artifact.artifact_id,
            state=GraphRunState(
                artifact_id=artifact.artifact_id,
                input_data=input_data,
                selected_agents=artifact.run_config.selected_agents,
                resolved_agents=artifact.run_config.resolved_agents,
                extracted_text=input_data.text,
                extracted_title=input_data.title,
                completed_nodes=["resolve_source"],
            ),
        )
    )

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.document is not None
    assert updated.status.value == "completed"
