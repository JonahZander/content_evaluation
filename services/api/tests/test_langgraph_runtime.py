"""LangGraph runtime tests."""

from __future__ import annotations

import pytest

from content_evaluation.domain.models import (
    ArtifactBlock,
    ContentFormat,
    GraphCheckpoint,
    GraphRunState,
    OrchestratorBackend,
    ProviderRoute,
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


class CrossParagraphAnalysisProvider(MockAnalysisProvider):
    """Return one finding that cannot be anchored into a single block."""

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        del instruction
        del title
        del blocks
        del context
        del route
        if agent_id == "value":
            return {
                "findings": [
                    {
                        "excerpt": "Alpha paragraph.\n\nBeta paragraph.",
                        "rationale": "This issue spans multiple paragraphs.",
                        "confidence": 0.81,
                        "suggestion": "Keep this as a bottom fallback until cross-block anchoring exists.",
                    }
                ]
            }
        return {"findings": []}


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
                extracted_content=input_data.text,
                extracted_title=input_data.title,
                extracted_content_format=ContentFormat.MARKDOWN,
                completed_nodes=["resolve_source"],
            ),
        )
    )

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.document is not None
    assert updated.status.value == "completed"


@pytest.mark.asyncio
async def test_unmatched_excerpts_append_bottom_reference_blocks() -> None:
    """Append unmatched references after the article instead of reusing the first block."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        CrossParagraphAnalysisProvider(),
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
        selected_agents=["value"],
    )
    artifact = await orchestrator.create_run(input_data)

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.document is not None
    assert updated.threads
    assert updated.document.blocks[-2].text == "Unmatched references"
    assert updated.document.blocks[-1].text == "Alpha paragraph.\n\nBeta paragraph."
    assert updated.threads[0].anchor.block_id == updated.document.blocks[-1].id
