"""Domain models for content evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class SourceType(StrEnum):
    """Enumerate supported source types."""

    URL = "url"
    TEXT = "text"
    FILE = "file"


class RunStatus(StrEnum):
    """Enumerate run lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuthorType(StrEnum):
    """Enumerate comment author types."""

    AGENT = "agent"
    HUMAN = "human"


class ReviewState(StrEnum):
    """Enumerate agent review states."""

    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class AgentCategory(StrEnum):
    """Enumerate analysis categories."""

    SIMILARITY = "similarity"
    AI_LIKELIHOOD = "ai_likelihood"
    VALUE = "value"
    AUDIENCE = "audience"
    EDITORIAL = "editorial"
    SYNTHESIS = "synthesis"
    HUMAN = "human"


class RunMetadata(BaseModel):
    """Store run identity and lifecycle metadata."""

    id: UUID = Field(default_factory=uuid4)
    status: RunStatus = RunStatus.QUEUED
    source_type: SourceType
    source_label: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    error_message: str | None = None


class DocumentBlock(BaseModel):
    """Store one normalized text block."""

    id: str = Field(default_factory=lambda: f"block-{uuid4()}")
    index: int
    text: str


class NormalizedDocument(BaseModel):
    """Store normalized reviewable content."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    source_type: SourceType
    source_label: str
    text: str
    blocks: list[DocumentBlock]


class TextAnchor(BaseModel):
    """Store a text-range anchor within one block."""

    id: str = Field(default_factory=lambda: f"anchor-{uuid4()}")
    block_id: str
    start_offset: int
    end_offset: int
    quote: str


class AgentFinding(BaseModel):
    """Store one structured agent finding."""

    id: str = Field(default_factory=lambda: f"finding-{uuid4()}")
    category: AgentCategory
    agent_name: str
    anchor_ids: list[str]
    rationale: str
    confidence: float
    model_name: str
    suggestion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommentReply(BaseModel):
    """Store one reply beneath a top-level comment."""

    id: str = Field(default_factory=lambda: f"reply-{uuid4()}")
    comment_id: str
    author_type: AuthorType
    author_label: str
    body: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class Comment(BaseModel):
    """Store one top-level comment tied to an anchor."""

    id: str = Field(default_factory=lambda: f"comment-{uuid4()}")
    run_id: UUID
    anchor_id: str
    author_type: AuthorType
    author_label: str
    category: AgentCategory
    body: str
    suggestion: str | None = None
    review_state: ReviewState = ReviewState.UNREVIEWED
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    replies: list[CommentReply] = Field(default_factory=list)


class CommentThread(BaseModel):
    """Store the comments for a single anchor."""

    anchor: TextAnchor
    comments: list[Comment]


class RunSummary(BaseModel):
    """Store aggregate scores and narrative summary."""

    overall_score: int
    verdict: str
    value_summary: str
    audience_summary: str
    novelty_score: float
    ai_likelihood: float


class RunEvent(BaseModel):
    """Store a durable run event."""

    id: str = Field(default_factory=lambda: f"event-{uuid4()}")
    run_id: UUID
    stage: str
    message: str
    status: str
    agent_name: str | None = None
    model_name: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunDetail(BaseModel):
    """Store the full UI payload for one run."""

    run: RunMetadata
    document: NormalizedDocument | None = None
    anchors: list[TextAnchor] = Field(default_factory=list)
    threads: list[CommentThread] = Field(default_factory=list)
    findings: list[AgentFinding] = Field(default_factory=list)
    summary: RunSummary | None = None
    events: list[RunEvent] = Field(default_factory=list)


class RunInput(BaseModel):
    """Store one input request for a run."""

    source_type: SourceType
    source_label: str
    text: str | None = None
    title: str | None = None
    url: str | None = None

