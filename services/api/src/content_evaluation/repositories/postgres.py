"""PostgreSQL repository implementation."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from content_evaluation.domain.exceptions import NotFoundError
from content_evaluation.domain.models import (
    AnalysisArtifact,
    GraphCheckpoint,
    RunJob,
    RunJobStatus,
    now_utc,
)


class PostgresRunRepository:
    """Persist artifacts to PostgreSQL with an optional read-through cache.

    Postgres is the single source of truth.  Write operations go to the
    database first; the in-memory cache is only updated on success.  Read
    operations check the cache first and fall back to a database query,
    always returning deep copies so callers cannot mutate cached state.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._pool: AsyncConnectionPool | None = None

        self._artifacts: dict[UUID, AnalysisArtifact] = {}
        self._jobs: dict[UUID, RunJob] = {}
        self._graph_checkpoints: dict[UUID, GraphCheckpoint] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create the PostgreSQL schema and open the connection pool."""

        self._pool = AsyncConnectionPool(self._database_url, min_size=2, max_size=10, open=False)
        await self._pool.open()

        statements = [
            """
            create table if not exists artifacts (
                id uuid primary key,
                payload jsonb not null
            )
            """,
            """
            create table if not exists run_jobs (
                artifact_id uuid primary key,
                payload jsonb not null
            )
            """,
            """
            create table if not exists graph_checkpoints (
                artifact_id uuid primary key,
                payload jsonb not null
            )
            """,
        ]
        async with self._pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    for statement in statements:
                        await cursor.execute(statement)

    async def close(self) -> None:
        """Close the connection pool."""

        if self._pool is not None:
            await self._pool.close()

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    async def create_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist a new artifact to PostgreSQL, then update the cache."""

        await self._upsert_json("artifacts", "id", str(artifact.artifact_id), artifact.model_dump(mode="json"))
        self._artifacts[artifact.artifact_id] = deepcopy(artifact)
        return deepcopy(artifact)

    async def update_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist an updated artifact snapshot to PostgreSQL, then update the cache."""

        artifact.updated_at = now_utc()
        await self._upsert_json("artifacts", "id", str(artifact.artifact_id), artifact.model_dump(mode="json"))
        self._artifacts[artifact.artifact_id] = deepcopy(artifact)
        return deepcopy(artifact)

    async def get_artifact(self, artifact_id: UUID) -> AnalysisArtifact | None:
        """Return one artifact, preferring cache and falling back to Postgres."""

        cached = self._artifacts.get(artifact_id)
        if cached is not None:
            return deepcopy(cached)

        assert self._pool is not None
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("select payload from artifacts where id = %s", (str(artifact_id),))
                row = await cursor.fetchone()
        if row is None:
            return None
        parsed = AnalysisArtifact.model_validate(row["payload"])
        self._artifacts[parsed.artifact_id] = deepcopy(parsed)
        return deepcopy(parsed)

    async def list_artifact_ids(self) -> list[UUID]:
        """Return all known artifact IDs from PostgreSQL."""

        assert self._pool is not None
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("select id from artifacts")
                rows = await cursor.fetchall()
        ids = {_coerce_uuid(row["id"]) for row in rows}
        ids.update(self._artifacts.keys())
        return list(ids)

    # ------------------------------------------------------------------
    # Run jobs
    # ------------------------------------------------------------------

    async def enqueue_run_job(self, job: RunJob) -> RunJob:
        """Persist a queued run job to Postgres first."""

        await self._upsert_json("run_jobs", "artifact_id", str(job.artifact_id), job.model_dump(mode="json"))
        self._jobs[job.artifact_id] = deepcopy(job)
        return deepcopy(job)

    async def claim_next_run_job(self) -> RunJob | None:
        """Claim the next queued run job (in-memory ordering, then persist)."""

        queued_jobs = sorted(
            (job for job in self._jobs.values() if job.status is RunJobStatus.QUEUED),
            key=lambda job: job.created_at,
        )
        if not queued_jobs:
            return None
        job = queued_jobs[0]
        job.status = RunJobStatus.RUNNING
        job.attempts += 1
        job.updated_at = now_utc()
        await self._upsert_json("run_jobs", "artifact_id", str(job.artifact_id), job.model_dump(mode="json"))
        return deepcopy(job)

    async def complete_run_job(self, artifact_id: UUID) -> None:
        """Mark one run job as completed in Postgres and cache."""

        job = self._jobs.get(artifact_id)
        if job is not None and job.status is not RunJobStatus.CANCELED:
            job.status = RunJobStatus.COMPLETED
            job.updated_at = now_utc()
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))

    async def fail_run_job(self, artifact_id: UUID) -> None:
        """Mark one run job as failed in Postgres and cache."""

        job = self._jobs.get(artifact_id)
        if job is None:
            raise NotFoundError(f"Run job {artifact_id} not found")
        if job.status is RunJobStatus.CANCELED:
            return
        job.status = RunJobStatus.FAILED
        job.updated_at = now_utc()
        await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))

    async def cancel_run_job(self, artifact_id: UUID) -> None:
        """Mark one run job as canceled in Postgres and cache."""

        job = self._jobs.get(artifact_id)
        if job is not None:
            job.status = RunJobStatus.CANCELED
            job.updated_at = now_utc()
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))

    async def requeue_run_job(self, artifact_id: UUID) -> RunJob | None:
        """Move one run job back to queued state."""

        job = self._jobs.get(artifact_id)
        if job is None:
            return None
        if job.status is RunJobStatus.CANCELED:
            return deepcopy(job)
        job.status = RunJobStatus.QUEUED
        job.updated_at = now_utc()
        await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))
        return deepcopy(job)

    async def reset_inflight_jobs(self) -> int:
        """Reset running jobs to queued state in both cache and Postgres."""

        reset_count = 0
        for job in self._jobs.values():
            if job.status is RunJobStatus.RUNNING:
                job.status = RunJobStatus.QUEUED
                job.updated_at = now_utc()
                reset_count += 1
        if reset_count > 0:
            for artifact_id, job in self._jobs.items():
                if job.status is RunJobStatus.QUEUED:
                    await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))
        return reset_count

    # ------------------------------------------------------------------
    # Graph checkpoints
    # ------------------------------------------------------------------

    async def save_graph_checkpoint(self, checkpoint: GraphCheckpoint) -> GraphCheckpoint:
        """Persist one graph checkpoint to Postgres first, then cache."""

        checkpoint.updated_at = now_utc()
        await self._upsert_json(
            "graph_checkpoints",
            "artifact_id",
            str(checkpoint.artifact_id),
            checkpoint.model_dump(mode="json"),
        )
        self._graph_checkpoints[checkpoint.artifact_id] = deepcopy(checkpoint)
        return deepcopy(checkpoint)

    async def get_graph_checkpoint(self, artifact_id: UUID) -> GraphCheckpoint | None:
        """Return one graph checkpoint, preferring cache then Postgres."""

        cached = self._graph_checkpoints.get(artifact_id)
        if cached is not None:
            return deepcopy(cached)

        assert self._pool is not None
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    "select payload from graph_checkpoints where artifact_id = %s",
                    (str(artifact_id),),
                )
                row = await cursor.fetchone()
        if row is None:
            return None
        parsed = GraphCheckpoint.model_validate(row["payload"])
        self._graph_checkpoints[artifact_id] = deepcopy(parsed)
        return deepcopy(parsed)

    async def delete_graph_checkpoint(self, artifact_id: UUID) -> None:
        """Delete one graph checkpoint from PostgreSQL and cache."""

        self._graph_checkpoints.pop(artifact_id, None)
        assert self._pool is not None
        async with self._pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    await cursor.execute("delete from graph_checkpoints where artifact_id = %s", (str(artifact_id),))

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    async def readiness_check(self) -> bool:
        """Return whether PostgreSQL is reachable."""

        try:
            assert self._pool is not None
            async with self._pool.connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("select 1")
                    await cursor.fetchone()
        except (psycopg.Error, AssertionError):
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upsert_json(self, table: str, key_column: str, key_value: str, payload: dict[str, object]) -> None:
        """Upsert one JSON payload into PostgreSQL inside a transaction."""

        assert self._pool is not None
        statement = sql.SQL(
            "insert into {table} ({key_col}, payload) values (%s, %s::jsonb) "
            "on conflict ({key_col}) do update set payload = excluded.payload"
        ).format(
            table=sql.Identifier(table),
            key_col=sql.Identifier(key_column),
        )
        async with self._pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    await cursor.execute(statement, (key_value, json.dumps(payload)))


def _coerce_uuid(value: UUID | str) -> UUID:
    """Normalize UUID values returned by psycopg row decoding."""

    if isinstance(value, UUID):
        return value
    return UUID(value)
