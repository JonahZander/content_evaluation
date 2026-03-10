"""In-memory repository implementation."""

from __future__ import annotations

from copy import deepcopy
from uuid import UUID

from content_evaluation.domain.exceptions import NotFoundError
from content_evaluation.domain.models import (
    AgentFinding,
    Comment,
    CommentReply,
    CommentThread,
    NormalizedDocument,
    ReviewState,
    RunDetail,
    RunEvent,
    RunMetadata,
    RunSummary,
    TextAnchor,
    now_utc,
)


class InMemoryRunRepository:
    """Persist run state in memory for tests and local fallback."""

    def __init__(self) -> None:
        """Initialize the in-memory store."""

        self._runs: dict[UUID, RunDetail] = {}

    async def create_run(self, run: RunMetadata) -> RunMetadata:
        """Persist a new run."""

        self._runs[run.id] = RunDetail(run=run)
        return run

    async def update_run(self, run: RunMetadata) -> RunMetadata:
        """Persist a run status change."""

        detail = self._require_run(run.id)
        detail.run = run
        return run

    async def save_document(self, run_id: UUID, document: NormalizedDocument) -> None:
        """Persist a normalized document for a run."""

        detail = self._require_run(run_id)
        detail.document = deepcopy(document)

    async def save_anchor(self, run_id: UUID, anchor: TextAnchor) -> TextAnchor:
        """Persist an anchor."""

        detail = self._require_run(run_id)
        detail.anchors = [existing for existing in detail.anchors if existing.id != anchor.id]
        detail.anchors.append(deepcopy(anchor))
        return anchor

    async def save_finding(self, run_id: UUID, finding: AgentFinding) -> AgentFinding:
        """Persist one finding."""

        detail = self._require_run(run_id)
        detail.findings.append(deepcopy(finding))
        return finding

    async def save_summary(self, run_id: UUID, summary: RunSummary) -> RunSummary:
        """Persist a run summary."""

        detail = self._require_run(run_id)
        detail.summary = deepcopy(summary)
        return summary

    async def save_comment(self, comment: Comment) -> Comment:
        """Persist a top-level comment."""

        detail = self._require_run(comment.run_id)
        anchor = self._require_anchor(detail, comment.anchor_id)
        thread = next((item for item in detail.threads if item.anchor.id == anchor.id), None)
        if thread is None:
            detail.threads.append(CommentThread(anchor=anchor, comments=[]))
            thread = detail.threads[-1]
        thread.comments = [existing for existing in thread.comments if existing.id != comment.id]
        thread.comments.append(deepcopy(comment))
        return comment

    async def update_comment(self, comment_id: str, body: str) -> Comment:
        """Update a human comment body."""

        comment = self._find_comment(comment_id)
        comment.body = body
        comment.updated_at = now_utc()
        return deepcopy(comment)

    async def delete_comment(self, comment_id: str) -> None:
        """Delete one human comment."""

        for detail in self._runs.values():
            for thread in detail.threads:
                filtered = [comment for comment in thread.comments if comment.id != comment_id]
                if len(filtered) != len(thread.comments):
                    thread.comments = filtered
                    return
        raise NotFoundError(f"Comment {comment_id} not found")

    async def add_reply(self, reply: CommentReply) -> CommentReply:
        """Persist one reply."""

        comment = self._find_comment(reply.comment_id)
        comment.replies.append(deepcopy(reply))
        return reply

    async def update_comment_review_state(self, comment_id: str, state: ReviewState) -> Comment:
        """Update a top-level comment review state."""

        comment = self._find_comment(comment_id)
        comment.review_state = state
        comment.updated_at = now_utc()
        return deepcopy(comment)

    async def append_event(self, event: RunEvent) -> RunEvent:
        """Persist one run event."""

        detail = self._require_run(event.run_id)
        detail.events.append(deepcopy(event))
        return event

    async def list_events(self, run_id: UUID) -> list[RunEvent]:
        """Return all events for one run."""

        return deepcopy(self._require_run(run_id).events)

    async def get_run_detail(self, run_id: UUID) -> RunDetail | None:
        """Return the full run detail payload."""

        detail = self._runs.get(run_id)
        return deepcopy(detail) if detail else None

    def _require_run(self, run_id: UUID) -> RunDetail:
        """Return a run detail or raise."""

        detail = self._runs.get(run_id)
        if detail is None:
            raise NotFoundError(f"Run {run_id} not found")
        return detail

    @staticmethod
    def _require_anchor(detail: RunDetail, anchor_id: str) -> TextAnchor:
        """Return an anchor or raise."""

        anchor = next((item for item in detail.anchors if item.id == anchor_id), None)
        if anchor is None:
            raise NotFoundError(f"Anchor {anchor_id} not found")
        return anchor

    def _find_comment(self, comment_id: str) -> Comment:
        """Return a comment or raise."""

        for detail in self._runs.values():
            for thread in detail.threads:
                for comment in thread.comments:
                    if comment.id == comment_id:
                        return comment
        raise NotFoundError(f"Comment {comment_id} not found")
