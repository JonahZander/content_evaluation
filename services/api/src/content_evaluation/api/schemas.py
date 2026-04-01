"""Transport schemas for FastAPI."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from content_evaluation.domain.models import (
    AnalysisArtifact,
    PersistenceMode,
    ReviewState,
    RevisedMarkdownDiffDecision,
    RevisionMode,
    SourceType,
)


class PreviewSourceRequest(BaseModel):
    """Store a request to preview normalized source content."""

    source_type: SourceType
    source_label: str
    title: str | None = None
    text: str | None = None
    url: str | None = None


class CreateRunRequest(PreviewSourceRequest):
    """Store a JSON request for a new run."""

    selected_agents: list[str] = Field(default_factory=list)
    persistence_mode: PersistenceMode = PersistenceMode.SESSION
    include_debug_trace: bool = False


class AppendAgentsRequest(BaseModel):
    """Store a request to append agent analyses to an existing artifact."""

    selected_agents: list[str] = Field(default_factory=list)


class ResearchRequest(BaseModel):
    """Store a request to queue targeted research."""

    prompt: str = Field(min_length=1)
    anchor_id: str | None = None
    comment_id: str | None = None


class GenerateRevisedMarkdownRequest(BaseModel):
    """Store a request to generate revised markdown."""

    mode: RevisionMode
    direction_prompt: str | None = None


class ImportArtifactRequest(BaseModel):
    """Store a request to import an artifact."""

    artifact: AnalysisArtifact


class CreateCommentRequest(BaseModel):
    """Store a request to create a comment."""

    artifact_id: UUID
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


class DiffReviewDecisionItem(BaseModel):
    """Store one diff-review decision."""

    diff_id: str
    decision: RevisedMarkdownDiffDecision


class UpdateDiffReviewRequest(BaseModel):
    """Store a request to update revised-markdown diff decisions."""

    decisions: list[DiffReviewDecisionItem] = Field(default_factory=list)
