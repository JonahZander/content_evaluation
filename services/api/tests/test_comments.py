"""Comment service tests."""

import pytest

from content_evaluation.domain.exceptions import ValidationError
from content_evaluation.domain.models import (
    AgentCategory,
    AnalysisArtifact,
    ArtifactAnchor,
    ArtifactBlock,
    ArtifactComment,
    ArtifactDocument,
    ArtifactSource,
    ArtifactThread,
    AuthorType,
    ReviewState,
    RunConfig,
    RuntimeMode,
    SourceType,
)
from content_evaluation.repositories.in_memory import InMemoryRunRepository
from content_evaluation.services.comments import CommentService


def _build_artifact() -> AnalysisArtifact:
    """Build one minimal artifact for comment tests."""

    block = ArtifactBlock(index=0, text="Test paragraph for comments.")
    anchor = ArtifactAnchor(block_id=block.id, start_offset=0, end_offset=4, quote="Test")
    artifact = AnalysisArtifact(
        source=ArtifactSource(source_type=SourceType.TEXT, source_label="draft"),
        document=ArtifactDocument(
            title="Draft",
            source_type=SourceType.TEXT,
            source_label="draft",
            text=block.text,
            blocks=[block],
        ),
        run_config=RunConfig(selected_agents=["editorial"], runtime_mode=RuntimeMode.MOCK),
        anchors=[anchor],
    )
    return artifact


@pytest.mark.asyncio
async def test_comment_service_creates_reply_and_review_state() -> None:
    """Create comments, replies, and review-state changes."""

    repository = InMemoryRunRepository()
    artifact = _build_artifact()
    await repository.create_artifact(artifact)
    anchor = artifact.anchors[0]
    agent_comment = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor.id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Trim this paragraph.",
    )
    artifact.threads = [ArtifactThread(anchor=anchor, comments=[agent_comment])]
    await repository.update_artifact(artifact)

    service = CommentService(repository, "Reviewer")
    human_comment = await service.create_comment(artifact.artifact_id, "I agree", anchor.id)
    reply = await service.add_reply(agent_comment.id, "Can you keep the example?")
    updated = await service.set_review_state(agent_comment.id, ReviewState.ACCEPTED)

    assert human_comment.author_label == "Reviewer"
    assert reply.body == "Can you keep the example?"
    assert updated.review_state is ReviewState.ACCEPTED


@pytest.mark.asyncio
async def test_comment_service_creates_new_anchor_for_human_selection() -> None:
    """Create a human comment from a new text selection."""

    repository = InMemoryRunRepository()
    artifact = _build_artifact()
    await repository.create_artifact(artifact)
    service = CommentService(repository, "Reviewer")

    comment = await service.create_comment(
        artifact.artifact_id,
        "New note",
        block_id=artifact.document.blocks[0].id,
        start_offset=2,
        end_offset=8,
        quote="sample",
    )
    updated = await repository.get_artifact(artifact.artifact_id)

    assert updated is not None
    assert comment.anchor_id in {anchor.id for anchor in updated.anchors}


@pytest.mark.asyncio
async def test_comment_service_rejects_editing_agent_comment() -> None:
    """Prevent edits to agent-authored comments."""

    repository = InMemoryRunRepository()
    artifact = _build_artifact()
    await repository.create_artifact(artifact)
    anchor = artifact.anchors[0]
    agent_comment = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor.id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Trim this paragraph.",
    )
    artifact.threads = [ArtifactThread(anchor=anchor, comments=[agent_comment])]
    await repository.update_artifact(artifact)

    service = CommentService(repository, "Reviewer")

    with pytest.raises(ValidationError, match="Only human comments can be edited"):
        await service.update_comment(agent_comment.id, "Changed")


@pytest.mark.asyncio
async def test_comment_service_rejects_reviewing_human_comment() -> None:
    """Prevent review-state updates on human comments."""

    repository = InMemoryRunRepository()
    artifact = _build_artifact()
    await repository.create_artifact(artifact)
    service = CommentService(repository, "Reviewer")
    human_comment = await service.create_comment(artifact.artifact_id, "Needs one example.", artifact.anchors[0].id)

    with pytest.raises(ValidationError, match="Only agent comments can receive review-state updates"):
        await service.set_review_state(human_comment.id, ReviewState.ACCEPTED)
