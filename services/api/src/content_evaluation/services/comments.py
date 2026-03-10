"""Comment service helpers."""

from __future__ import annotations

from uuid import UUID

from content_evaluation.domain.exceptions import NotFoundError, ValidationError
from content_evaluation.domain.models import (
    AgentCategory,
    AnalysisArtifact,
    ArtifactAnchor,
    ArtifactComment,
    ArtifactReply,
    ArtifactThread,
    AuthorType,
    ReviewState,
    now_utc,
)
from content_evaluation.repositories.base import RunRepository


class CommentService:
    """Manage standalone comments, replies, and review-state changes."""

    def __init__(self, repository: RunRepository, reviewer_name: str) -> None:
        """Initialize the comment service."""

        self._repository = repository
        self._reviewer_name = reviewer_name

    async def create_comment(
        self,
        artifact_id: UUID,
        body: str,
        anchor_id: str | None = None,
        *,
        block_id: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
        quote: str | None = None,
    ) -> ArtifactComment:
        """Create one human standalone comment."""

        artifact = await self._require_artifact(artifact_id)
        resolved_anchor_id = anchor_id
        if resolved_anchor_id is None:
            if block_id is None or start_offset is None or end_offset is None or quote is None:
                raise ValidationError("A new anchor requires block_id, start_offset, end_offset, and quote")
            anchor = ArtifactAnchor(
                block_id=block_id,
                start_offset=start_offset,
                end_offset=end_offset,
                quote=quote,
            )
            artifact.anchors.append(anchor)
            resolved_anchor_id = anchor.id

        comment = ArtifactComment(
            artifact_id=artifact_id,
            anchor_id=resolved_anchor_id,
            author_type=AuthorType.HUMAN,
            author_label=self._reviewer_name,
            category=AgentCategory.HUMAN,
            body=body,
        )
        thread = _require_thread_for_anchor(artifact, resolved_anchor_id)
        thread.comments.append(comment)
        await self._repository.update_artifact(artifact)
        return comment

    async def update_comment(self, comment_id: str, body: str) -> ArtifactComment:
        """Update one human standalone comment."""

        artifact, comment = await self._find_comment(comment_id)
        if comment.author_type is not AuthorType.HUMAN:
            raise ValidationError("Only human comments can be edited")
        comment.body = body
        comment.updated_at = now_utc()
        await self._repository.update_artifact(artifact)
        return comment

    async def delete_comment(self, comment_id: str) -> None:
        """Delete one human standalone comment."""

        artifact, comment = await self._find_comment(comment_id)
        if comment.author_type is not AuthorType.HUMAN:
            raise ValidationError("Only human comments can be deleted")
        for thread in artifact.threads:
            next_comments = [item for item in thread.comments if item.id != comment_id]
            if len(next_comments) != len(thread.comments):
                thread.comments = next_comments
                break
        artifact.threads = [thread for thread in artifact.threads if thread.comments]
        await self._repository.update_artifact(artifact)

    async def add_reply(self, comment_id: str, body: str) -> ArtifactReply:
        """Add one human reply beneath a comment."""

        artifact, comment = await self._find_comment(comment_id)
        reply = ArtifactReply(
            comment_id=comment_id,
            author_type=AuthorType.HUMAN,
            author_label=self._reviewer_name,
            body=body,
        )
        comment.replies.append(reply)
        comment.updated_at = now_utc()
        await self._repository.update_artifact(artifact)
        return reply

    async def set_review_state(self, comment_id: str, state: ReviewState) -> ArtifactComment:
        """Set the review state for one agent comment."""

        if state is ReviewState.UNREVIEWED:
            raise ValidationError("Review state must be accepted, rejected, or uncertain")
        artifact, comment = await self._find_comment(comment_id)
        if comment.author_type is not AuthorType.AGENT:
            raise ValidationError("Only agent comments can receive review-state updates")
        comment.review_state = state
        comment.updated_at = now_utc()
        await self._repository.update_artifact(artifact)
        return comment

    async def _require_artifact(self, artifact_id: UUID) -> AnalysisArtifact:
        """Return one artifact or raise."""

        artifact = await self._repository.get_artifact(artifact_id)
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")
        return artifact

    async def _find_comment(self, comment_id: str) -> tuple[AnalysisArtifact, ArtifactComment]:
        """Return one comment plus its artifact."""

        for artifact_id in getattr(self._repository, "_artifacts", {}):
            artifact = await self._repository.get_artifact(artifact_id)
            if artifact is None:
                continue
            for thread in artifact.threads:
                for comment in thread.comments:
                    if comment.id == comment_id:
                        return artifact, comment
        raise NotFoundError(f"Comment {comment_id} not found")


def _require_thread_for_anchor(artifact: AnalysisArtifact, anchor_id: str) -> ArtifactThread:
    """Return the thread for one anchor, creating it if needed."""

    anchor = next((item for item in artifact.anchors if item.id == anchor_id), None)
    if anchor is None:
        raise NotFoundError(f"Anchor {anchor_id} not found")
    thread = next((item for item in artifact.threads if item.anchor.id == anchor_id), None)
    if thread is None:
        thread = ArtifactThread(anchor=anchor, comments=[])
        artifact.threads.append(thread)
    return thread
