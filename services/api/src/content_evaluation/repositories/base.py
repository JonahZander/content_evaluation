"""Repository interfaces."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from content_evaluation.domain.models import (
    AgentFinding,
    Comment,
    CommentReply,
    NormalizedDocument,
    ReviewState,
    RunDetail,
    RunEvent,
    RunJob,
    RunMetadata,
    RunSummary,
    TextAnchor,
)


class RunRepository(Protocol):
    """Describe storage operations for runs and comments."""

    async def create_run(self, run: RunMetadata) -> RunMetadata:
        """Persist a new run."""

    async def enqueue_run_job(self, job: RunJob) -> RunJob:
        """Persist a queued job."""

    async def claim_next_run_job(self) -> RunJob | None:
        """Claim the next queued job for worker processing."""

    async def complete_run_job(self, run_id: UUID) -> None:
        """Mark one queued job as completed."""

    async def fail_run_job(self, run_id: UUID) -> None:
        """Mark one queued job as failed."""

    async def requeue_run_job(self, run_id: UUID) -> RunJob | None:
        """Return a failed/running job back to the queue."""

    async def reset_inflight_jobs(self) -> int:
        """Reset running jobs when the worker starts."""

    async def update_run(self, run: RunMetadata) -> RunMetadata:
        """Persist a run status change."""

    async def save_document(self, run_id: UUID, document: NormalizedDocument) -> None:
        """Persist a normalized document for a run."""

    async def save_anchor(self, run_id: UUID, anchor: TextAnchor) -> TextAnchor:
        """Persist an anchor."""

    async def save_finding(self, run_id: UUID, finding: AgentFinding) -> AgentFinding:
        """Persist one structured finding."""

    async def save_summary(self, run_id: UUID, summary: RunSummary) -> RunSummary:
        """Persist one run summary."""

    async def save_comment(self, comment: Comment) -> Comment:
        """Persist one top-level comment."""

    async def update_comment(self, comment_id: str, body: str) -> Comment:
        """Update a human comment body."""

    async def delete_comment(self, comment_id: str) -> None:
        """Delete one human comment."""

    async def get_comment(self, comment_id: str) -> Comment:
        """Return one top-level comment."""

    async def add_reply(self, reply: CommentReply) -> CommentReply:
        """Persist one comment reply."""

    async def update_comment_review_state(self, comment_id: str, state: ReviewState) -> Comment:
        """Update a top-level comment review state."""

    async def append_event(self, event: RunEvent) -> RunEvent:
        """Persist one run event."""

    async def list_events(self, run_id: UUID) -> list[RunEvent]:
        """Return all events for one run."""

    async def get_run_detail(self, run_id: UUID) -> RunDetail | None:
        """Return the full run detail payload."""

    async def readiness_check(self) -> bool:
        """Return whether the storage backend is ready."""
