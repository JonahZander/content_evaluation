"""Tests for revised-markdown generation and diff review."""

from __future__ import annotations

import pytest

from content_evaluation.domain.exceptions import ValidationError
from content_evaluation.domain.models import (
    OrchestratorBackend,
    RevisionMode,
    RevisedMarkdownDiffDecision,
    ReviewState,
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
from content_evaluation.services.orchestration import RunOrchestrator


def _orchestrator() -> RunOrchestrator:
    """Build a mock orchestrator for revised-markdown tests."""

    repository = InMemoryRunRepository()
    return RunOrchestrator(
        repository,
        MockAnalysisProvider(),
        MockSimilaritySearchProvider(),
        MockContentExtractionProvider(),
        RuntimeMode.MOCK,
        False,
        OrchestratorBackend.LANGGRAPH,
        deep_research_provider=MockDeepResearchProvider(),
    )


@pytest.mark.asyncio
async def test_generate_revised_markdown_requires_accepted_suggestions() -> None:
    """Reject revised-markdown generation until an agent suggestion is accepted."""

    orchestrator = _orchestrator()
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        )
    )
    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        ),
    )

    with pytest.raises(ValidationError):
        await orchestrator.generate_revised_markdown(artifact.artifact_id, mode=RevisionMode.SURGICAL)


@pytest.mark.asyncio
async def test_generate_revised_markdown_builds_candidate_and_diff_review() -> None:
    """Generate revised markdown and deterministic diff data from accepted suggestions."""

    orchestrator = _orchestrator()
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        )
    )
    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        ),
    )

    stored = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    stored.threads[0].comments[0].review_state = ReviewState.ACCEPTED
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    updated = await orchestrator.generate_revised_markdown(artifact.artifact_id, mode=RevisionMode.SURGICAL)

    assert updated.revised_document is not None
    assert updated.diff_review is not None
    assert updated.revised_document.mode is RevisionMode.SURGICAL
    assert updated.diff_review.original_markdown == updated.document.raw_content
    assert updated.diff_review.candidate_markdown == updated.revised_document.markdown
    assert updated.diff_review.diff_items


@pytest.mark.asyncio
async def test_generate_revised_markdown_persists_rewrite_mode_and_direction() -> None:
    """Persist rewrite-mode metadata on the candidate revision payload."""

    orchestrator = _orchestrator()
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        )
    )
    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        ),
    )

    stored = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    stored.threads[0].comments[0].review_state = ReviewState.ACCEPTED
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    updated = await orchestrator.generate_revised_markdown(
        artifact.artifact_id,
        mode=RevisionMode.REWRITE,
        direction_prompt="Lead with the strongest evidence.",
    )

    assert updated.revised_document is not None
    assert updated.diff_review is not None
    assert updated.revised_document.mode is RevisionMode.REWRITE
    assert updated.revised_document.direction_prompt == "Lead with the strongest evidence."
    assert updated.diff_review.mode is RevisionMode.REWRITE
    assert updated.diff_review.direction_prompt == "Lead with the strongest evidence."


@pytest.mark.asyncio
async def test_apply_diff_review_promotes_revised_markdown_only_after_decisions() -> None:
    """Require reviewed diff decisions before replacing canonical markdown."""

    orchestrator = _orchestrator()
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        )
    )
    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["editorial"],
        ),
    )

    stored = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    stored.threads[0].comments[0].review_state = ReviewState.ACCEPTED
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001
    await orchestrator.generate_revised_markdown(artifact.artifact_id, mode=RevisionMode.SURGICAL)

    with pytest.raises(ValidationError):
        await orchestrator.apply_diff_review(artifact.artifact_id)

    generated = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    decisions = [
        (item.id, RevisedMarkdownDiffDecision.ACCEPTED)
        for item in generated.diff_review.diff_items
    ]
    await orchestrator.update_diff_review(artifact.artifact_id, decisions)

    applied = await orchestrator.apply_diff_review(artifact.artifact_id)

    assert applied.document is not None
    assert all(result.category.value in {"fact_check", "research"} for result in applied.agent_results)
    assert applied.agent_plan == []
    assert applied.summary is None
    assert applied.review_summary is None


@pytest.mark.asyncio
async def test_apply_diff_review_preserves_historical_fact_check_only_for_previous_revision() -> None:
    """Preserve fact-check history across apply without reusing it as current revision input."""

    orchestrator = _orchestrator()
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["fact_check", "editorial"],
        )
    )
    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["fact_check", "editorial"],
        ),
    )

    stored = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    for thread in stored.threads:
        for comment in thread.comments:
            if comment.suggestion:
                comment.review_state = ReviewState.ACCEPTED
    previous_revision_id = stored.document.revision_id if stored.document is not None else None
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    generated = await orchestrator.generate_revised_markdown(artifact.artifact_id, mode=RevisionMode.SURGICAL)
    await orchestrator.update_diff_review(
        artifact.artifact_id,
        [(item.id, RevisedMarkdownDiffDecision.ACCEPTED) for item in generated.diff_review.diff_items],
    )
    applied = await orchestrator.apply_diff_review(artifact.artifact_id)

    assert applied.document is not None
    assert previous_revision_id is not None
    assert applied.document.revision_id != previous_revision_id
    assert applied.previous_draft_snapshot is not None
    assert applied.previous_draft_snapshot.document.revision_id == previous_revision_id
    assert all(result.category.value in {"fact_check", "research"} for result in applied.agent_results)
    assert all(result.document_revision_id == previous_revision_id for result in applied.agent_results)
    assert all(comment.document_revision_id == previous_revision_id for thread in applied.threads for comment in thread.comments)

    with pytest.raises(ValidationError):
        await orchestrator.generate_revised_markdown(applied.artifact_id, mode=RevisionMode.SURGICAL)
