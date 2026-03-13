"""PostgreSQL repository implementation."""

from __future__ import annotations

import json
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from content_evaluation.domain.models import AnalysisArtifact, GraphCheckpoint, RunJob
from content_evaluation.repositories.in_memory import InMemoryRunRepository


class PostgresRunRepository(InMemoryRunRepository):
    """Persist artifacts to PostgreSQL and mirror them in memory for fast reads."""

    def __init__(self, database_url: str) -> None:
        """Initialize the PostgreSQL repository."""

        super().__init__()
        self._database_url = database_url
        self._pool: AsyncConnectionPool | None = None

    async def initialize(self) -> None:
        """Create the PostgreSQL schema and open the connection pool."""

        self._pool = AsyncConnectionPool(self._database_url, min_size=2, max_size=10)
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
            async with connection.cursor() as cursor:
                for statement in statements:
                    await cursor.execute(statement)
            await connection.commit()

    async def close(self) -> None:
        """Close the connection pool."""

        if self._pool is not None:
            await self._pool.close()

    async def create_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist a new artifact to PostgreSQL and memory."""

        created = await super().create_artifact(artifact)
        await self._upsert_json("artifacts", "id", str(artifact.artifact_id), artifact.model_dump(mode="json"))
        return created

    async def update_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist an updated artifact to PostgreSQL and memory."""

        updated = await super().update_artifact(artifact)
        await self._upsert_json("artifacts", "id", str(artifact.artifact_id), updated.model_dump(mode="json"))
        return updated

    async def get_artifact(self, artifact_id: UUID) -> AnalysisArtifact | None:
        """Return one artifact, reading from PostgreSQL when memory is empty."""

        artifact = await super().get_artifact(artifact_id)
        if artifact is not None:
            return artifact
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("select payload from artifacts where id = %s", (str(artifact_id),))
                row = await cursor.fetchone()
        if row is None:
            return None
        parsed = AnalysisArtifact.model_validate(row["payload"])
        self._artifacts[parsed.artifact_id] = parsed
        return parsed

    async def enqueue_run_job(self, job: RunJob) -> RunJob:
        """Persist a queued run job."""

        queued = await super().enqueue_run_job(job)
        await self._upsert_json("run_jobs", "artifact_id", str(job.artifact_id), job.model_dump(mode="json"))
        return queued

    async def claim_next_run_job(self) -> RunJob | None:
        """Claim the next queued run job."""

        job = await super().claim_next_run_job()
        if job is not None:
            await self._upsert_json("run_jobs", "artifact_id", str(job.artifact_id), job.model_dump(mode="json"))
        return job

    async def complete_run_job(self, artifact_id: UUID) -> None:
        """Mark one run job as completed."""

        await super().complete_run_job(artifact_id)
        job = self._jobs.get(artifact_id)
        if job is not None:
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))

    async def fail_run_job(self, artifact_id: UUID) -> None:
        """Mark one run job as failed."""

        await super().fail_run_job(artifact_id)
        job = self._jobs.get(artifact_id)
        if job is not None:
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))

    async def cancel_run_job(self, artifact_id: UUID) -> None:
        """Mark one run job as canceled."""

        await super().cancel_run_job(artifact_id)
        job = self._jobs.get(artifact_id)
        if job is not None:
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))

    async def requeue_run_job(self, artifact_id: UUID) -> RunJob | None:
        """Move one run job back to queued state."""

        job = await super().requeue_run_job(artifact_id)
        if job is not None:
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))
        return job

    async def reset_inflight_jobs(self) -> int:
        """Reset running jobs in PostgreSQL and memory."""

        reset_count = await super().reset_inflight_jobs()
        for artifact_id, job in self._jobs.items():
            await self._upsert_json("run_jobs", "artifact_id", str(artifact_id), job.model_dump(mode="json"))
        return reset_count

    async def readiness_check(self) -> bool:
        """Return whether PostgreSQL is reachable."""

        try:
            async with self._pool.connection() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("select 1")
                    await cursor.fetchone()
        except psycopg.Error:
            return False
        return True

    async def save_graph_checkpoint(self, checkpoint: GraphCheckpoint) -> GraphCheckpoint:
        """Persist one graph checkpoint."""

        self._graph_checkpoints[checkpoint.artifact_id] = checkpoint
        await self._upsert_json(
            "graph_checkpoints",
            "artifact_id",
            str(checkpoint.artifact_id),
            checkpoint.model_dump(mode="json"),
        )
        return checkpoint

    async def get_graph_checkpoint(self, artifact_id: UUID) -> GraphCheckpoint | None:
        """Return one graph checkpoint, loading from PostgreSQL if needed."""

        checkpoint = self._graph_checkpoints.get(artifact_id)
        if checkpoint is not None:
            return checkpoint
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
        self._graph_checkpoints[artifact_id] = parsed
        return parsed

    async def delete_graph_checkpoint(self, artifact_id: UUID) -> None:
        """Delete one graph checkpoint from PostgreSQL and memory."""

        self._graph_checkpoints.pop(artifact_id, None)
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("delete from graph_checkpoints where artifact_id = %s", (str(artifact_id),))
            await connection.commit()

    async def list_artifact_ids(self) -> list[UUID]:
        """Return all known artifact IDs from memory and PostgreSQL."""

        ids = set(self._artifacts.keys())
        async with self._pool.connection() as connection:
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("select id from artifacts")
                rows = await cursor.fetchall()
        for row in rows:
            ids.add(UUID(row["id"]))
        return list(ids)

    async def _upsert_json(self, table: str, key_column: str, key_value: str, payload: dict[str, object]) -> None:
        """Upsert one JSON payload into PostgreSQL."""

        statement = sql.SQL(
            "insert into {table} ({key_col}, payload) values (%s, %s::jsonb) "
            "on conflict ({key_col}) do update set payload = excluded.payload"
        ).format(
            table=sql.Identifier(table),
            key_col=sql.Identifier(key_column),
        )
        async with self._pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(statement, (key_value, json.dumps(payload)))
            await connection.commit()
