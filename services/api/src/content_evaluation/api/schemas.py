"""Transport schemas for FastAPI."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from content_evaluation.domain.models import ReviewState, SourceType


class CreateRunRequest(BaseModel):
    """Store a JSON request for a new run."""

    source_type: SourceType
    source_label: str
    title: str | None = None
    text: str | None = None
    url: str | None = None


class CreateCommentRequest(BaseModel):
    """Store a request to create a comment."""

    run_id: UUID
    anchor_id: str | None = None
    block_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    quote: str | None = None
    body: str = Field(min_length=1)


class UpdateCommentRequest(BaseModel):
    """Store a request to update a comment."""

    body: str = Field(min_length=1)


class CreateReplyRequest(BaseModel):
    """Store a request to create a reply."""

    body: str = Field(min_length=1)


class UpdateReviewStateRequest(BaseModel):
    """Store a request to update review state."""

    review_state: ReviewState
