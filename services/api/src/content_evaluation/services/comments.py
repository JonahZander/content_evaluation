"""Comment service helpers."""

from __future__ import annotations

from uuid import UUID

from content_evaluation.domain.exceptions import ValidationError
from content_evaluation.domain.models import AgentCategory, AuthorType, Comment, CommentReply, ReviewState, TextAnchor
from content_evaluation.repositories.base import RunRepository


class CommentService:
    """Manage standalone comments, replies, and review-state changes."""

    def __init__(self, repository: RunRepository, reviewer_name: str) -> None:
        """Initialize the comment service."""

        self._repository = repository
        self._reviewer_name = reviewer_name

    async def create_comment(
        self,
        run_id: UUID,
        body: str,
        anchor_id: str | None = None,
        *,
        block_id: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        quote: str | None = None,
    ) -> Comment:
        """Create one human standalone comment."""

        resolved_anchor_id = anchor_id
        if resolved_anchor_id is None:
            if block_id is None or start_offset is None or end_offset is None or quote is None:
                raise ValidationError("A new anchor requires block_id, start_offset, end_offset, and quote")
            anchor = TextAnchor(
                block_id=block_id,
                start_offset=start_offset,
                end_offset=end_offset,
                quote=quote,
            )
            await self._repository.save_anchor(run_id, anchor)
            resolved_anchor_id = anchor.id

        comment = Comment(
            run_id=run_id,
            anchor_id=resolved_anchor_id,
            author_type=AuthorType.HUMAN,
            author_label=self._reviewer_name,
            category=AgentCategory.HUMAN,
            body=body,
        )
        return await self._repository.save_comment(comment)

    async def update_comment(self, comment_id: str, body: str) -> Comment:
        """Update one human standalone comment."""

        comment = await self._repository.get_comment(comment_id)
        if comment.author_type is not AuthorType.HUMAN:
            raise ValidationError("Only human comments can be edited")
        return await self._repository.update_comment(comment_id, body)

    async def delete_comment(self, comment_id: str) -> None:
        """Delete one human standalone comment."""

        comment = await self._repository.get_comment(comment_id)
        if comment.author_type is not AuthorType.HUMAN:
            raise ValidationError("Only human comments can be deleted")
        await self._repository.delete_comment(comment_id)

    async def add_reply(self, comment_id: str, body: str) -> CommentReply:
        """Add one human reply beneath a comment."""

        await self._repository.get_comment(comment_id)
        reply = CommentReply(
            comment_id=comment_id,
            author_type=AuthorType.HUMAN,
            author_label=self._reviewer_name,
            body=body,
        )
        return await self._repository.add_reply(reply)

    async def set_review_state(self, comment_id: str, state: ReviewState) -> Comment:
        """Set the review state for one agent comment."""

        if state is ReviewState.UNREVIEWED:
            raise ValidationError("Review state must be accepted, rejected, or uncertain")
        comment = await self._repository.get_comment(comment_id)
        if comment.author_type is not AuthorType.AGENT:
            raise ValidationError("Only agent comments can receive review-state updates")
        return await self._repository.update_comment_review_state(comment_id, state)
