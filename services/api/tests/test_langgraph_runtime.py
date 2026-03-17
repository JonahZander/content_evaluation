"""LangGraph runtime tests."""

from __future__ import annotations

import pytest

from content_evaluation.domain.exceptions import ProviderError
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
    MockDeepResearchProvider,
    MockSimilaritySearchProvider,
)
from content_evaluation.repositories.in_memory import InMemoryRunRepository
from content_evaluation.services.orchestration import RunOrchestrator, _result_context_payload


class CrossParagraphAnalysisProvider(MockAnalysisProvider):
    """Return one finding that spans adjacent paragraphs."""

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
                        "rationale": "This issue spans adjacent paragraphs.",
                        "confidence": 0.81,
                        "suggestion": "Keep the linked review span across both paragraphs.",
                    }
                ]
            }
        return {"findings": []}


class DistantCrossParagraphAnalysisProvider(MockAnalysisProvider):
    """Return one finding that can only match across non-adjacent blocks."""

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
                        "excerpt": "Alpha paragraph.\n\nGamma paragraph.",
                        "rationale": "This issue can only be described across distant sections.",
                        "confidence": 0.62,
                    }
                ]
            }
        return {"findings": []}


class ContaminatedContextAnalysisProvider(MockAnalysisProvider):
    """Assert that unmatched fallback excerpts are not replayed as article context."""

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
        del route
        if agent_id == "value":
            return {
                "findings": [
                    {
                        "excerpt": "Alpha paragraph.\n\nGamma paragraph.",
                        "rationale": "This still should be unmatched.",
                        "confidence": 0.62,
                    }
                ]
            }
        if agent_id == "synthesis":
            assert context is not None
            value_context = context.get("value") or next(iter(context.values()))
            assert "raw_output" not in value_context
            finding_context = next(
                item
                for item in value_context["findings"]
                if item.get("metadata", {}).get("matched_to_source") is False
                or "unmatched_excerpt" in item
            )
            assert finding_context["metadata"]["matched_to_source"] is False
            assert "excerpt" not in finding_context["metadata"]
            assert finding_context["unmatched_excerpt"] == "Alpha paragraph.\n\nGamma paragraph."
        return {"findings": []}


class RetryOnceAnalysisProvider(MockAnalysisProvider):
    """Fail once with a retriable provider timeout before succeeding."""

    def __init__(self) -> None:
        super().__init__()
        self._attempts = 0

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        self._attempts += 1
        if self._attempts == 1:
            raise ProviderError(
                "LangChain analysis request failed: Request timed out.",
                kind="timeout",
                retriable=True,
                provider_name="openai",
            )
        return await super().analyze(agent_id, instruction, title, blocks, context, route)


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
        deep_research_provider=MockDeepResearchProvider(),
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
        deep_research_provider=MockDeepResearchProvider(),
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
    assert any(event.status == "resumed" for event in updated.events)


@pytest.mark.asyncio
async def test_retriable_agent_timeout_retries_without_run_resume() -> None:
    """Retry one transient provider timeout inside the agent execution loop."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        RetryOnceAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
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
    assert updated.status.value == "completed"
    assert any(event.status == "retrying" and event.error_kind == "timeout" for event in updated.events)
    assert not any(event.status == "resumed" for event in updated.events)


@pytest.mark.asyncio
async def test_adjacent_cross_paragraph_excerpts_anchor_to_source_blocks() -> None:
    """Resolve adjacent cross-paragraph excerpts into multi-segment source anchors."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        CrossParagraphAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
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
    assert not any(block.text == "Unmatched references" for block in updated.document.blocks)
    assert updated.threads[0].anchor.match_kind.value == "source"
    assert len(updated.threads[0].anchor.segments) == 2
    assert updated.threads[0].anchor.segments[0].block_id == updated.document.blocks[0].id
    assert updated.threads[0].anchor.segments[1].block_id == updated.document.blocks[1].id


@pytest.mark.asyncio
async def test_distant_cross_paragraph_excerpts_stay_unmatched() -> None:
    """Keep distant cross-paragraph excerpts in the bottom unmatched section."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        DistantCrossParagraphAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
    )
    input_data = RunInput(
        source_type=SourceType.TEXT,
        source_label="Draft",
        title="Draft",
        text="Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph.",
        selected_agents=["value"],
    )
    artifact = await orchestrator.create_run(input_data)

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.document is not None
    assert updated.threads
    assert updated.document.blocks[-2].text == "Unmatched references"
    assert updated.document.blocks[-1].origin.value == "synthetic_unmatched"
    assert updated.threads[0].anchor.match_kind.value == "synthetic_unmatched"


@pytest.mark.asyncio
async def test_downstream_context_excludes_synthetic_unmatched_excerpt_metadata() -> None:
    """Keep unmatched fallback prose out of dependency payloads for later agents."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        ContaminatedContextAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
    )
    input_data = RunInput(
        source_type=SourceType.TEXT,
        source_label="Draft",
        title="Draft",
        text="Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph.",
        selected_agents=["value"],
    )
    artifact = await orchestrator.create_run(input_data)

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    value_result = next(result for result in updated.agent_results if result.agent_id == "value")
    payload = _result_context_payload(updated, value_result)
    assert "raw_output" not in payload
    finding_context = payload["findings"][0]
    assert finding_context["metadata"]["matched_to_source"] is False
    assert "excerpt" not in finding_context["metadata"]
    assert finding_context["unmatched_excerpt"] == "Alpha paragraph.\n\nGamma paragraph."


@pytest.mark.asyncio
async def test_agent_result_metadata_includes_usage() -> None:
    """ArtifactAgentResult.metadata must carry usage after orchestration threads it through."""
    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
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
    analysis_results = [
        r for r in updated.agent_results
        if r.agent_id not in ("similarity", "fact_check")
    ]
    assert analysis_results, "No analysis agent results found"
    for result in analysis_results:
        usage = result.metadata.get("usage")
        assert usage is not None, f"Agent {result.agent_id} has no usage in metadata"
        assert usage["input_tokens"] == 10
        assert usage["output_tokens"] == 5
        assert usage["total_tokens"] == 15


@pytest.mark.asyncio
async def test_completed_run_builds_review_summary_and_keeps_fact_check_out_of_threads() -> None:
    """Fact-check data should feed the summary surface without cluttering the thread rail."""

    repository = InMemoryRunRepository()
    orchestrator = RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
    )
    input_data = RunInput(
        source_type=SourceType.TEXT,
        source_label="Draft",
        title="Draft",
        text="Alpha paragraph.\n\nBeta paragraph.",
    )
    artifact = await orchestrator.create_run(input_data)

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.review_summary is not None
    assert updated.review_summary.research_summary
    assert updated.review_summary.overlap_items
    assert not any(
        comment.category.value == "fact_check"
        for thread in updated.threads
        for comment in thread.comments
    )
    assert not any(
        comment.category.value == "audience"
        for thread in updated.threads
        for comment in thread.comments
    )
