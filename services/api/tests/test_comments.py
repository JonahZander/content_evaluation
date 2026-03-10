"""Comment service tests."""

from uuid import uuid4

import pytest

from content_evaluation.domain.models import AgentCategory, AuthorType, Comment, ReviewState, RunMetadata, SourceType, TextAnchor
from content_evaluation.repositories.in_memory import InMemoryRunRepository
from content_evaluation.services.comments import CommentService


@pytest.mark.asyncio
async def test_comment_service_creates_reply_and_review_state() -> None:
    """Create comments, replies, and review-state changes."""

    repository = InMemoryRunRepository()
    run = RunMetadata(source_type=SourceType.TEXT, source_label="draft")
    await repository.create_run(run)
    anchor = TextAnchor(block_id="block-1", start_offset=0, end_offset=4, quote="Test")
    await repository.save_anchor(run.id, anchor)
    agent_comment = Comment(
        run_id=run.id,
        anchor_id=anchor.id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Trim this paragraph.",
    )
    await repository.save_comment(agent_comment)

    service = CommentService(repository, "Reviewer")
    human_comment = await service.create_comment(run.id, "I agree", anchor.id)
    reply = await service.add_reply(agent_comment.id, "Can you keep the example?")
    updated = await service.set_review_state(agent_comment.id, ReviewState.ACCEPTED)

    assert human_comment.author_label == "Reviewer"
    assert reply.body == "Can you keep the example?"
    assert updated.review_state is ReviewState.ACCEPTED


@pytest.mark.asyncio
async def test_comment_service_creates_new_anchor_for_human_selection() -> None:
    """Create a human comment from a new text selection."""

    repository = InMemoryRunRepository()
    run = RunMetadata(source_type=SourceType.TEXT, source_label="draft")
    await repository.create_run(run)
    service = CommentService(repository, "Reviewer")

    comment = await service.create_comment(
        run.id,
        "New note",
        block_id="block-1",
        start_offset=2,
        end_offset=8,
        quote="sample",
    )
    detail = await repository.get_run_detail(run.id)

    assert comment.anchor_id in {anchor.id for anchor in detail.anchors}
