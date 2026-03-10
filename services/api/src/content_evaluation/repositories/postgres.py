"""PostgreSQL repository implementation."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

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
)
from content_evaluation.repositories.in_memory import InMemoryRunRepository


class PostgresRunRepository(InMemoryRunRepository):
    """Persist runs to PostgreSQL while keeping domain mapping simple."""

    def __init__(self, database_url: str) -> None:
        """Initialize the PostgreSQL repository."""

        super().__init__()
        self._database_url = database_url

    async def initialize(self) -> None:
        """Create the minimal PostgreSQL schema."""

        statements = [
            """
            create table if not exists analysis_runs (
                id uuid primary key,
                payload jsonb not null
            )
            """,
            """
            create table if not exists documents (
                id uuid primary key,
                run_id uuid not null unique,
                payload jsonb not null
            )
            """,
            """
            create table if not exists document_blocks (
                id text primary key,
                run_id uuid not null,
                payload jsonb not null
            )
            """,
            """
            create table if not exists anchors (
                id text primary key,
                run_id uuid not null,
                payload jsonb not null
            )
            """,
            """
            create table if not exists comments (
                id text primary key,
                run_id uuid not null,
                payload jsonb not null
            )
            """,
            """
            create table if not exists comment_replies (
                id text primary key,
                run_id uuid not null,
                comment_id text not null,
                payload jsonb not null
            )
            """,
            """
            create table if not exists findings (
                id text primary key,
                run_id uuid not null,
                payload jsonb not null
            )
            """,
            """
            create table if not exists summaries (
                run_id uuid primary key,
                payload jsonb not null
            )
            """,
            """
            create table if not exists run_events (
                id text primary key,
                run_id uuid not null,
                payload jsonb not null
            )
            """,
        ]

        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()

    async def create_run(self, run: RunMetadata) -> RunMetadata:
        """Persist a new run to PostgreSQL and memory."""

        await super().create_run(run)
        await self._execute_upsert("analysis_runs", str(run.id), run.model_dump(mode="json"))
        return run

    async def update_run(self, run: RunMetadata) -> RunMetadata:
        """Persist a run update to PostgreSQL and memory."""

        await super().update_run(run)
        await self._execute_upsert("analysis_runs", str(run.id), run.model_dump(mode="json"))
        return run

    async def save_document(self, run_id: UUID, document: NormalizedDocument) -> None:
        """Persist a document to PostgreSQL and memory."""

        await super().save_document(run_id, document)
        await self._execute_upsert("documents", str(document.id), {"run_id": str(run_id), **document.model_dump(mode="json")})
        for block in document.blocks:
            await self._execute_upsert(
                "document_blocks",
                block.id,
                {"run_id": str(run_id), **block.model_dump(mode="json")},
            )

    async def save_anchor(self, run_id: UUID, anchor: TextAnchor) -> TextAnchor:
        """Persist an anchor to PostgreSQL and memory."""

        await super().save_anchor(run_id, anchor)
        await self._execute_upsert("anchors", anchor.id, {"run_id": str(run_id), **anchor.model_dump(mode="json")})
        return anchor

    async def save_finding(self, run_id: UUID, finding: AgentFinding) -> AgentFinding:
        """Persist a finding to PostgreSQL and memory."""

        await super().save_finding(run_id, finding)
        await self._execute_upsert("findings", finding.id, {"run_id": str(run_id), **finding.model_dump(mode="json")})
        return finding

    async def save_summary(self, run_id: UUID, summary: RunSummary) -> RunSummary:
        """Persist a summary to PostgreSQL and memory."""

        await super().save_summary(run_id, summary)
        await self._execute_upsert("summaries", str(run_id), summary.model_dump(mode="json"))
        return summary

    async def save_comment(self, comment: Comment) -> Comment:
        """Persist a comment to PostgreSQL and memory."""

        await super().save_comment(comment)
        await self._execute_upsert("comments", comment.id, {"run_id": str(comment.run_id), **comment.model_dump(mode="json")})
        return comment

    async def update_comment(self, comment_id: str, body: str) -> Comment:
        """Update a comment in PostgreSQL and memory."""

        comment = await super().update_comment(comment_id, body)
        await self._execute_upsert("comments", comment.id, {"run_id": str(comment.run_id), **comment.model_dump(mode="json")})
        return comment

    async def delete_comment(self, comment_id: str) -> None:
        """Delete a comment from PostgreSQL and memory."""

        await super().delete_comment(comment_id)
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from comments where id = %s", (comment_id,))
                cursor.execute("delete from comment_replies where comment_id = %s", (comment_id,))
            connection.commit()

    async def add_reply(self, reply: CommentReply) -> CommentReply:
        """Persist a reply to PostgreSQL and memory."""

        await super().add_reply(reply)
        detail = self._find_comment(reply.comment_id)
        await self._execute_upsert(
            "comment_replies",
            reply.id,
            {"run_id": str(detail.run_id), "comment_id": reply.comment_id, **reply.model_dump(mode="json")},
        )
        return reply

    async def update_comment_review_state(self, comment_id: str, state: ReviewState) -> Comment:
        """Update review state in PostgreSQL and memory."""

        comment = await super().update_comment_review_state(comment_id, state)
        await self._execute_upsert("comments", comment.id, {"run_id": str(comment.run_id), **comment.model_dump(mode="json")})
        return comment

    async def append_event(self, event: RunEvent) -> RunEvent:
        """Persist an event to PostgreSQL and memory."""

        await super().append_event(event)
        await self._execute_upsert("run_events", event.id, {"run_id": str(event.run_id), **event.model_dump(mode="json")})
        return event

    async def get_run_detail(self, run_id: UUID) -> RunDetail | None:
        """Return a run detail, falling back to PostgreSQL when needed."""

        detail = await super().get_run_detail(run_id)
        if detail is not None:
            return detail

        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select payload from analysis_runs where id = %s", (str(run_id),))
                run_row = cursor.fetchone()
                if run_row is None:
                    return None
                run = RunMetadata.model_validate(run_row["payload"])

                cursor.execute("select payload from documents where run_id = %s", (str(run_id),))
                document_row = cursor.fetchone()
                document = NormalizedDocument.model_validate(document_row["payload"]) if document_row else None

                cursor.execute("select payload from anchors where run_id = %s", (str(run_id),))
                anchors = [TextAnchor.model_validate(row["payload"]) for row in cursor.fetchall()]

                cursor.execute("select payload from findings where run_id = %s", (str(run_id),))
                findings = [AgentFinding.model_validate(row["payload"]) for row in cursor.fetchall()]

                cursor.execute("select payload from summaries where run_id = %s", (str(run_id),))
                summary_row = cursor.fetchone()
                summary = RunSummary.model_validate(summary_row["payload"]) if summary_row else None

                cursor.execute("select payload from comments where run_id = %s", (str(run_id),))
                comments = [Comment.model_validate(row["payload"]) for row in cursor.fetchall()]

                cursor.execute("select payload from comment_replies where run_id = %s", (str(run_id),))
                replies = [CommentReply.model_validate(row["payload"]) for row in cursor.fetchall()]

                reply_map: dict[str, list[CommentReply]] = {}
                for reply in replies:
                    reply_map.setdefault(reply.comment_id, []).append(reply)
                for comment in comments:
                    comment.replies = reply_map.get(comment.id, [])

                thread_map: dict[str, CommentThread] = {}
                anchor_map = {anchor.id: anchor for anchor in anchors}
                for comment in comments:
                    anchor = anchor_map[comment.anchor_id]
                    thread = thread_map.get(anchor.id)
                    if thread is None:
                        thread = CommentThread(anchor=anchor, comments=[])
                        thread_map[anchor.id] = thread
                    thread.comments.append(comment)

                cursor.execute("select payload from run_events where run_id = %s", (str(run_id),))
                events = [RunEvent.model_validate(row["payload"]) for row in cursor.fetchall()]

        return RunDetail(run=run, document=document, anchors=anchors, threads=list(thread_map.values()), findings=findings, summary=summary, events=events)

    async def _execute_upsert(self, table: str, row_id: str, payload: dict[str, Any]) -> None:
        """Upsert a JSON payload into one PostgreSQL table."""

        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"insert into {table} (id, payload) values (%s, %s::jsonb) "
                    f"on conflict (id) do update set payload = excluded.payload",
                    (row_id, json.dumps(payload)),
                )
            connection.commit()
