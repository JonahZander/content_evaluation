"""Tests for revised-markdown generation and diff review."""

from __future__ import annotations

from uuid import UUID

import pytest

from content_evaluation.domain.exceptions import ValidationError
from content_evaluation.domain.models import (
    AgentCategory,
    AnalysisArtifact,
    ArtifactComment,
    ArtifactDiffItem,
    ArtifactDiffReview,
    ArtifactReply,
    AuthorType,
    OrchestratorBackend,
    ReviewState,
    RevisedMarkdownDiffDecision,
    RevisionMode,
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


async def _build_editorial_artifact(orchestrator: RunOrchestrator) -> AnalysisArtifact:
    """Create and process one minimal editorial artifact for revision tests."""

    input_data = RunInput(
        source_type=SourceType.TEXT,
        source_label="Draft",
        title="Draft",
        text="Alpha paragraph.\n\nBeta paragraph.",
        selected_agents=["editorial"],
    )
    artifact = await orchestrator.create_run(input_data)
    await orchestrator.process_run(artifact.artifact_id, input_data)
    return await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001


async def _capture_revision_payload(
    orchestrator: RunOrchestrator,
    artifact_id: UUID,
) -> list[dict[str, object]]:
    """Capture the accepted-suggestion payload sent to revised-markdown generation."""

    captured: list[list[dict[str, object]]] = []
    original = orchestrator._analysis_provider.generate_revised_markdown  # noqa: SLF001

    async def _spy(
        original_markdown: str,
        accepted_suggestions: list[dict[str, object]],
        mode: RevisionMode,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.append(accepted_suggestions)
        return await original(original_markdown, accepted_suggestions, mode, **kwargs)

    orchestrator._analysis_provider.generate_revised_markdown = _spy  # type: ignore[method-assign]  # noqa: SLF001
    await orchestrator.generate_revised_markdown(artifact_id, mode=RevisionMode.SURGICAL)

    assert captured, "expected provider to be invoked"
    return captured[0]


def _render_applied_markdown(diff_review: ArtifactDiffReview) -> str:
    """Render the markdown produced by the stored diff decisions."""

    original_lines = diff_review.original_markdown.splitlines()
    applied_lines: list[str] = []
    cursor = 0
    for item in sorted(
        diff_review.diff_items,
        key=lambda diff: (diff.original_start_line, diff.original_end_line, diff.id),
    ):
        start = max(0, item.original_start_line - 1)
        end = max(start, item.original_end_line)
        applied_lines.extend(original_lines[cursor:start])
        if item.decision is RevisedMarkdownDiffDecision.ACCEPTED:
            applied_lines.extend(item.after_text.splitlines())
        else:
            applied_lines.extend(original_lines[start:end])
        cursor = end
    applied_lines.extend(original_lines[cursor:])
    return "\n".join(applied_lines).strip()


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
async def test_generate_revised_markdown_forwards_comment_sources_to_provider() -> None:
    """Forward accepted-comment `sources` into the revised-markdown provider payload."""

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

    citation = "https://example.com/survey"
    stored = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    stored.threads[0].comments[0].review_state = ReviewState.ACCEPTED
    stored.threads[0].comments[0].sources = [citation]
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    captured: list[list[dict[str, object]]] = []
    original = orchestrator._analysis_provider.generate_revised_markdown  # noqa: SLF001

    async def _spy(
        original_markdown: str,
        accepted_suggestions: list[dict[str, object]],
        mode: RevisionMode,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.append(accepted_suggestions)
        return await original(original_markdown, accepted_suggestions, mode, **kwargs)

    orchestrator._analysis_provider.generate_revised_markdown = _spy  # type: ignore[method-assign]  # noqa: SLF001

    await orchestrator.generate_revised_markdown(artifact.artifact_id, mode=RevisionMode.SURGICAL)

    assert captured, "expected provider to be invoked"
    payload = captured[0]
    assert payload, "expected at least one accepted suggestion"
    assert payload[0].get("sources") == [citation]


@pytest.mark.asyncio
async def test_generate_revised_markdown_forwards_human_replies_as_reviewer_notes() -> None:
    """Forward human replies on accepted agent comments as reviewer notes."""

    orchestrator = _orchestrator()
    stored = await _build_editorial_artifact(orchestrator)
    assert stored.document is not None

    comment = stored.threads[0].comments[0]
    comment.review_state = ReviewState.ACCEPTED
    comment.replies.extend(
        [
            ArtifactReply(
                comment_id=comment.id,
                author_type=AuthorType.HUMAN,
                author_label="Workspace reviewer",
                body="Please keep the phrase plain language intact.",
            ),
            ArtifactReply(
                comment_id=comment.id,
                author_type=AuthorType.HUMAN,
                author_label="Workspace reviewer",
                body="Keep the subheading short.",
            ),
        ]
    )
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    payload = await _capture_revision_payload(orchestrator, stored.artifact_id)

    assert payload[0]["comment_id"] == comment.id
    assert payload[0]["reviewer_notes"] == [
        "Please keep the phrase plain language intact.",
        "Keep the subheading short.",
    ]


@pytest.mark.asyncio
async def test_generate_revised_markdown_forwards_standalone_human_comments() -> None:
    """Forward standalone human comments as direct reviewer instructions."""

    orchestrator = _orchestrator()
    stored = await _build_editorial_artifact(orchestrator)
    assert stored.document is not None

    stored.threads[0].comments[0].review_state = ReviewState.ACCEPTED
    human_comment = ArtifactComment(
        artifact_id=stored.artifact_id,
        anchor_id=stored.threads[0].anchor.id,
        document_revision_id=stored.document.revision_id,
        author_type=AuthorType.HUMAN,
        author_label="Workspace reviewer",
        category=AgentCategory.HUMAN,
        body="Replace this with a direct call-to-action.",
    )
    stored.threads[0].comments.append(human_comment)
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    payload = await _capture_revision_payload(orchestrator, stored.artifact_id)
    human_item = next(item for item in payload if item["comment_id"] == human_comment.id)

    assert human_item["comment"] == "Replace this with a direct call-to-action."
    assert human_item["suggestion"] == ""
    assert human_item["reviewer_notes"] == []
    assert human_item["author_label"] == "Workspace reviewer"


@pytest.mark.asyncio
async def test_generate_revised_markdown_skips_replies_under_rejected_or_uncertain_comments() -> None:
    """Ignore human replies that sit under non-accepted agent comments."""

    orchestrator = _orchestrator()
    stored = await _build_editorial_artifact(orchestrator)
    assert stored.document is not None

    accepted_comment = stored.threads[0].comments[0]
    accepted_comment.review_state = ReviewState.ACCEPTED
    rejected_comment = ArtifactComment(
        artifact_id=stored.artifact_id,
        anchor_id=stored.threads[0].anchor.id,
        document_revision_id=stored.document.revision_id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Rejected note.",
        suggestion="Rejected suggestion.",
        review_state=ReviewState.REJECTED,
        replies=[
            ArtifactReply(
                comment_id="placeholder",
                author_type=AuthorType.HUMAN,
                author_label="Workspace reviewer",
                body="Do not forward this rejected reply.",
            )
        ],
    )
    rejected_comment.replies[0].comment_id = rejected_comment.id
    uncertain_comment = ArtifactComment(
        artifact_id=stored.artifact_id,
        anchor_id=stored.threads[0].anchor.id,
        document_revision_id=stored.document.revision_id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Uncertain note.",
        suggestion="Uncertain suggestion.",
        review_state=ReviewState.UNCERTAIN,
        replies=[
            ArtifactReply(
                comment_id="placeholder",
                author_type=AuthorType.HUMAN,
                author_label="Workspace reviewer",
                body="Do not forward this uncertain reply.",
            )
        ],
    )
    uncertain_comment.replies[0].comment_id = uncertain_comment.id
    stored.threads[0].comments.extend([rejected_comment, uncertain_comment])
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    payload = await _capture_revision_payload(orchestrator, stored.artifact_id)

    payload_ids = {item["comment_id"] for item in payload}
    reviewer_notes = [note for item in payload for note in item.get("reviewer_notes", [])]

    assert accepted_comment.id in payload_ids
    assert rejected_comment.id not in payload_ids
    assert uncertain_comment.id not in payload_ids
    assert "Do not forward this rejected reply." not in reviewer_notes
    assert "Do not forward this uncertain reply." not in reviewer_notes


@pytest.mark.asyncio
async def test_generate_revised_markdown_skips_empty_human_comments() -> None:
    """Skip standalone human comments whose bodies compact down to empty text."""

    orchestrator = _orchestrator()
    stored = await _build_editorial_artifact(orchestrator)
    assert stored.document is not None

    stored.threads[0].comments[0].review_state = ReviewState.ACCEPTED
    empty_comment = ArtifactComment(
        artifact_id=stored.artifact_id,
        anchor_id=stored.threads[0].anchor.id,
        document_revision_id=stored.document.revision_id,
        author_type=AuthorType.HUMAN,
        author_label="Workspace reviewer",
        category=AgentCategory.HUMAN,
        body=" \n\t ",
    )
    stored.threads[0].comments.append(empty_comment)
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    payload = await _capture_revision_payload(orchestrator, stored.artifact_id)

    assert all(item["comment_id"] != empty_comment.id for item in payload)


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
async def test_apply_diff_review_applies_only_accepted_diffs_when_some_remain_pending() -> None:
    """Apply accepted diffs while keeping rejected and pending text unchanged."""

    orchestrator = _orchestrator()
    artifact = await orchestrator.create_run(
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["ai_likelihood", "editorial"],
        )
    )
    await orchestrator.process_run(
        artifact.artifact_id,
        RunInput(
            source_type=SourceType.TEXT,
            source_label="Draft",
            title="Draft",
            text="Alpha paragraph.\n\nBeta paragraph.",
            selected_agents=["ai_likelihood", "editorial"],
        ),
    )

    stored = await orchestrator._require_artifact(artifact.artifact_id)  # noqa: SLF001
    for thread in stored.threads:
        for comment in thread.comments:
            if comment.suggestion:
                comment.review_state = ReviewState.ACCEPTED
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001
    generated = await orchestrator.generate_revised_markdown(
        artifact.artifact_id,
        mode=RevisionMode.REWRITE,
        direction_prompt="Lead with the strongest evidence.",
    )

    assert generated.diff_review is not None
    assert len(generated.diff_review.diff_items) >= 2

    decisions = [
        (generated.diff_review.diff_items[0].id, RevisedMarkdownDiffDecision.ACCEPTED),
        (generated.diff_review.diff_items[1].id, RevisedMarkdownDiffDecision.REJECTED),
    ]
    reviewed = await orchestrator.update_diff_review(artifact.artifact_id, decisions)
    line_count = len(reviewed.diff_review.original_markdown.splitlines())
    reviewed.diff_review.diff_items.append(
        ArtifactDiffItem(
            change_type="insert",
            original_start_line=line_count + 1,
            original_end_line=line_count,
            candidate_start_line=line_count + 1,
            candidate_end_line=line_count + 1,
            before_text="",
            after_text="Synthetic pending insertion.",
        )
    )
    await orchestrator._repository.update_artifact(reviewed)  # noqa: SLF001
    assert any(item.decision is RevisedMarkdownDiffDecision.PENDING for item in reviewed.diff_review.diff_items)

    applied = await orchestrator.apply_diff_review(artifact.artifact_id)
    assert applied.document is not None
    assert applied.document.raw_content == _render_applied_markdown(reviewed.diff_review)

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
    assert all(
        comment.document_revision_id == previous_revision_id
        for thread in applied.previous_draft_snapshot.threads
        for comment in thread.comments
    )

    with pytest.raises(ValidationError):
        await orchestrator.generate_revised_markdown(applied.artifact_id, mode=RevisionMode.SURGICAL)


@pytest.mark.asyncio
async def test_apply_diff_review_keeps_historical_threads_only_in_snapshot() -> None:
    """Historical fact-check threads stay in previous_draft_snapshot, not the live artifact."""

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
    await orchestrator._repository.update_artifact(stored)  # noqa: SLF001

    generated = await orchestrator.generate_revised_markdown(artifact.artifact_id, mode=RevisionMode.SURGICAL)
    await orchestrator.update_diff_review(
        artifact.artifact_id,
        [(item.id, RevisedMarkdownDiffDecision.ACCEPTED) for item in generated.diff_review.diff_items],
    )

    applied = await orchestrator.apply_diff_review(artifact.artifact_id)
    assert applied.document is not None
    current_revision_id = applied.document.revision_id
    for thread in applied.threads:
        assert thread.document_revision_id in (None, current_revision_id), (
            f"Thread {thread.anchor.id} has document_revision_id {thread.document_revision_id} "
            f"but the live article should only contain threads tied to {current_revision_id}"
        )
    assert applied.previous_draft_snapshot is not None


@pytest.mark.asyncio
async def test_apply_diff_review_rewrite_all_pending_uses_full_candidate() -> None:
    """Apply the full rewrite candidate when no per-diff decisions are recorded."""

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

    generated = await orchestrator.generate_revised_markdown(
        artifact.artifact_id,
        mode=RevisionMode.REWRITE,
        direction_prompt="Lead with the strongest evidence.",
    )
    assert generated.diff_review is not None
    candidate_markdown = generated.diff_review.candidate_markdown
    assert all(
        item.decision is RevisedMarkdownDiffDecision.PENDING
        for item in generated.diff_review.diff_items
    )

    applied = await orchestrator.apply_diff_review(artifact.artifact_id)

    assert applied.document is not None
    assert applied.document.raw_content == candidate_markdown.strip()
