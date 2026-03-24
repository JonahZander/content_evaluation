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
    RunMode,
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
        del context
        del route
        if agent_id == "editorial":
            return {
                "findings": [
                    {
                        "excerpt": "Alpha paragraph.\n\nBeta paragraph.",
                        "block_id": blocks[0].id if blocks else None,
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
        del context
        del route
        if agent_id == "editorial":
            return {
                "findings": [
                    {
                        "excerpt": "Alpha paragraph.\n\nGamma paragraph.",
                        "block_id": blocks[0].id if blocks else None,
                        "rationale": "This issue can only be described across distant sections.",
                        "confidence": 0.62,
                    }
                ]
            }
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
        selected_agents=["ai_likelihood"],
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
        selected_agents=["editorial"],
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
        selected_agents=["editorial"],
    )
    artifact = await orchestrator.create_run(input_data)

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.document is not None
    assert updated.threads
    has_unmatched_thread = any(thread.anchor.match_kind.value == "synthetic_unmatched" for thread in updated.threads)
    if has_unmatched_thread:
        assert updated.document.blocks[-2].text == "Unmatched references"
        assert updated.document.blocks[-1].origin.value == "synthetic_unmatched"
    else:
        assert not any(block.text == "Unmatched references" for block in updated.document.blocks)
        assert any(thread.anchor.match_kind.value == "source" for thread in updated.threads)


@pytest.mark.asyncio
async def test_downstream_context_excludes_synthetic_unmatched_excerpt_metadata() -> None:
    """Keep unmatched fallback prose out of dependency payloads for later agents."""

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
        selected_agents=["editorial"],
    )
    artifact = await orchestrator.create_run(input_data)

    await orchestrator.process_run(artifact.artifact_id, input_data)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    editorial_result = next(result for result in updated.agent_results if result.agent_id == "editorial")
    payload = _result_context_payload(updated, editorial_result)
    assert "raw_output" not in payload
    finding_context = payload["findings"][0]
    if finding_context["metadata"]["matched_to_source"] is False:
        assert "excerpt" not in finding_context["metadata"]
        assert finding_context["unmatched_excerpt"] == "Alpha paragraph.\n\nGamma paragraph."
    else:
        assert finding_context["metadata"]["matched_to_source"] is True
        assert "unmatched_excerpt" not in finding_context


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
async def test_completed_run_builds_review_summary_and_puts_fact_check_in_threads() -> None:
    """Fact-check data should appear in the shared comment rail and still feed the summary."""

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
    assert updated.review_summary.tl_dr
    assert updated.review_summary.research_summary
    assert updated.review_summary.word_count > 0
    assert updated.review_summary.estimated_reading_time_minutes >= 1
    assert updated.review_summary.overlap_items
    fact_check_comments = [
        comment
        for thread in updated.threads
        for comment in thread.comments
        if comment.category.value == "fact_check"
    ]
    assert fact_check_comments
    assert fact_check_comments[0].metadata.get("verdict") is not None
    assert fact_check_comments[0].metadata.get("evidence_summary")


@pytest.mark.asyncio
async def test_append_agents_reuses_existing_artifact_and_runs_only_missing_dependencies() -> None:
    """Append analysis should keep completed work and run only newly required agents."""

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
        selected_agents=["ai_likelihood"],
    )
    artifact = await orchestrator.create_run(input_data)
    await orchestrator.process_run(artifact.artifact_id, input_data)

    queued_artifact, append_input = await orchestrator.append_agents(artifact.artifact_id, ["editorial"])
    assert queued_artifact.status.value == "queued"
    assert append_input.mode is RunMode.APPEND_AGENTS

    await orchestrator.process_run(artifact.artifact_id, append_input)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.status.value == "completed"
    assert updated.document is not None
    assert [result.agent_id for result in updated.agent_results].count("ai_likelihood") == 1
    assert {result.agent_id for result in updated.agent_results} >= {"ai_likelihood", "fact_check", "editorial"}
    assert updated.run_config.selected_agents == ["ai_likelihood", "editorial"]
    assert updated.run_config.resolved_agents == ["ai_likelihood", "fact_check", "editorial"]
    assert any(event.message == "Additional analysis queued" for event in updated.events)
    assert any(event.message == "Additional analysis completed" for event in updated.events)


@pytest.mark.asyncio
async def test_append_agents_can_schedule_new_agents_after_dependencies_already_completed() -> None:
    """Append analysis should treat prior completed agents as satisfied dependencies."""

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
        selected_agents=["fact_check"],
    )
    artifact = await orchestrator.create_run(input_data)
    await orchestrator.process_run(artifact.artifact_id, input_data)

    queued_artifact, append_input = await orchestrator.append_agents(
        artifact.artifact_id,
        ["editorial"],
    )
    assert queued_artifact.status.value == "queued"
    assert append_input.mode is RunMode.APPEND_AGENTS

    await orchestrator.process_run(artifact.artifact_id, append_input)

    updated = await repository.get_artifact(artifact.artifact_id)
    assert updated is not None
    assert updated.status.value == "completed"
    assert updated.document is not None
    assert {result.agent_id for result in updated.agent_results} >= {
        "fact_check",
        "ai_likelihood",
        "editorial",
    }
    assert updated.run_config.selected_agents == ["fact_check", "editorial"]


@pytest.mark.asyncio
async def test_targeted_research_appends_without_replacing_prior_research_findings() -> None:
    """Targeted research should add new research comments instead of overwriting old ones."""

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
    target_comment = next(
        comment
        for thread in updated.threads
        for comment in thread.comments
        if comment.category.value == "fact_check"
    )

    queued_artifact, research_input = await orchestrator.research(
        artifact.artifact_id,
        "Verify the primary claim in this section.",
        comment_id=target_comment.id,
    )
    assert queued_artifact.status.value == "queued"
    assert research_input.mode is RunMode.RESEARCH

    await orchestrator.process_run(artifact.artifact_id, research_input)

    _, second_research_input = await orchestrator.research(
        artifact.artifact_id,
        "Check whether the supporting example is current.",
        comment_id=target_comment.id,
    )
    await orchestrator.process_run(artifact.artifact_id, second_research_input)

    final_artifact = await repository.get_artifact(artifact.artifact_id)
    assert final_artifact is not None
    research_results = [result for result in final_artifact.agent_results if result.agent_id == "research"]
    assert len(research_results) == 2
    research_comments = [
        comment
        for thread in final_artifact.threads
        for comment in thread.comments
        if comment.category.value == "research"
    ]
    assert len(research_comments) == 2
