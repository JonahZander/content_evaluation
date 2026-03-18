"""PostgresRunRepository tests using a mock async connection pool.

These tests validate the Postgres-first write semantics, deepcopy cache
isolation, job lifecycle transitions, and readiness checks without
requiring a running Postgres instance.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from content_evaluation.domain.models import (
    AnalysisArtifact,
    ArtifactBlock,
    ArtifactDocument,
    ArtifactSource,
    GraphCheckpoint,
    GraphRunState,
    RunConfig,
    RunInput,
    RunJob,
    RunJobStatus,
    RuntimeMode,
    SourceType,
)
from content_evaluation.repositories.postgres import PostgresRunRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_artifact() -> AnalysisArtifact:
    block = ArtifactBlock(index=0, text="Test paragraph.")
    return AnalysisArtifact(
        source=ArtifactSource(source_type=SourceType.TEXT, source_label="draft"),
        document=ArtifactDocument(
            title="Draft",
            source_type=SourceType.TEXT,
            source_label="draft",
            text=block.text,
            blocks=[block],
        ),
        run_config=RunConfig(selected_agents=["editorial"], runtime_mode=RuntimeMode.MOCK),
    )


def _build_run_job(artifact_id=None) -> RunJob:
    return RunJob(
        artifact_id=artifact_id or uuid4(),
        input_data=RunInput(source_type=SourceType.TEXT, source_label="draft", text="Test."),
    )


class FakeCursor:
    """Minimal async cursor that records SQL and returns canned rows."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []
        self.executed: list[tuple[Any, ...]] = []

    async def execute(self, query: Any, params: Any = None) -> None:
        self.executed.append((query, params))

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    async def __aenter__(self) -> "FakeCursor":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass


class FakeTransaction:
    """Minimal async transaction context manager."""

    async def __aenter__(self) -> "FakeTransaction":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass


class FakeConnection:
    """Minimal async connection that returns FakeCursor instances."""

    def __init__(self, cursor: FakeCursor | None = None) -> None:
        self._cursor = cursor or FakeCursor()

    def cursor(self, **_kwargs: Any) -> FakeCursor:
        return self._cursor

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def commit(self) -> None:
        pass

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass


class FakePool:
    """Minimal async connection pool stub."""

    def __init__(self, connection: FakeConnection | None = None) -> None:
        self._connection = connection or FakeConnection()

    def connection(self) -> FakeConnection:
        return self._connection

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


def _repo_with_pool(pool: FakePool | None = None) -> PostgresRunRepository:
    repo = PostgresRunRepository("postgres://test:test@localhost/test")
    repo._pool = pool or FakePool()  # noqa: SLF001
    return repo


# ---------------------------------------------------------------------------
# Artifact CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_constructs_pool_without_auto_open() -> None:
    repo = PostgresRunRepository("postgres://test:test@localhost/test")
    fake_pool = FakePool()

    with patch("content_evaluation.repositories.postgres.AsyncConnectionPool", return_value=fake_pool) as pool_class:
        await repo.initialize()

    pool_class.assert_called_once_with("postgres://test:test@localhost/test", min_size=2, max_size=10, open=False)


@pytest.mark.asyncio
async def test_create_artifact_writes_to_postgres_and_cache() -> None:
    repo = _repo_with_pool()
    artifact = _build_artifact()

    created = await repo.create_artifact(artifact)

    assert created.artifact_id == artifact.artifact_id
    assert repo._artifacts[artifact.artifact_id] is not artifact


@pytest.mark.asyncio
async def test_get_artifact_returns_deepcopy_from_cache() -> None:
    repo = _repo_with_pool()
    artifact = _build_artifact()
    await repo.create_artifact(artifact)

    first = await repo.get_artifact(artifact.artifact_id)
    second = await repo.get_artifact(artifact.artifact_id)

    assert first is not second
    assert first is not None and second is not None
    assert first.artifact_id == second.artifact_id


@pytest.mark.asyncio
async def test_get_artifact_falls_back_to_postgres() -> None:
    artifact = _build_artifact()
    payload = artifact.model_dump(mode="json")
    cursor = FakeCursor(rows=[{"payload": payload}])
    pool = FakePool(FakeConnection(cursor))
    repo = _repo_with_pool(pool)

    fetched = await repo.get_artifact(artifact.artifact_id)

    assert fetched is not None
    assert fetched.artifact_id == artifact.artifact_id
    assert artifact.artifact_id in repo._artifacts


@pytest.mark.asyncio
async def test_get_artifact_returns_none_for_missing() -> None:
    cursor = FakeCursor(rows=[])
    pool = FakePool(FakeConnection(cursor))
    repo = _repo_with_pool(pool)

    assert await repo.get_artifact(uuid4()) is None


@pytest.mark.asyncio
async def test_list_artifact_ids_accepts_native_uuid_rows() -> None:
    artifact_id = uuid4()
    cursor = FakeCursor(rows=[{"id": artifact_id}])
    pool = FakePool(FakeConnection(cursor))
    repo = _repo_with_pool(pool)

    assert await repo.list_artifact_ids() == [artifact_id]


@pytest.mark.asyncio
async def test_update_artifact_persists_to_postgres_then_cache() -> None:
    repo = _repo_with_pool()
    artifact = _build_artifact()
    await repo.create_artifact(artifact)

    artifact.error_message = "Something broke"
    updated = await repo.update_artifact(artifact)

    assert updated.error_message == "Something broke"
    cached = repo._artifacts[artifact.artifact_id]
    assert cached.error_message == "Something broke"


@pytest.mark.asyncio
async def test_cache_isolation_after_create() -> None:
    """Mutations to the returned artifact must not affect the cache."""

    repo = _repo_with_pool()
    artifact = _build_artifact()
    created = await repo.create_artifact(artifact)

    created.error_message = "mutated"
    cached = repo._artifacts[artifact.artifact_id]
    assert cached.error_message is None


@pytest.mark.asyncio
async def test_list_artifact_ids_merges_cache_and_postgres() -> None:
    pg_id = uuid4()
    cursor = FakeCursor(rows=[{"id": str(pg_id)}])
    pool = FakePool(FakeConnection(cursor))
    repo = _repo_with_pool(pool)

    artifact = _build_artifact()
    await repo.create_artifact(artifact)

    ids = await repo.list_artifact_ids()
    assert artifact.artifact_id in ids
    assert pg_id in ids


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_and_claim_job() -> None:
    repo = _repo_with_pool()
    job = _build_run_job()
    await repo.enqueue_run_job(job)

    claimed = await repo.claim_next_run_job()

    assert claimed is not None
    assert claimed.artifact_id == job.artifact_id
    assert claimed.status is RunJobStatus.RUNNING
    assert claimed.attempts == 1


@pytest.mark.asyncio
async def test_claim_returns_none_when_empty() -> None:
    repo = _repo_with_pool()
    assert await repo.claim_next_run_job() is None


@pytest.mark.asyncio
async def test_complete_job() -> None:
    repo = _repo_with_pool()
    job = _build_run_job()
    await repo.enqueue_run_job(job)
    await repo.claim_next_run_job()

    await repo.complete_run_job(job.artifact_id)

    assert repo._jobs[job.artifact_id].status is RunJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_fail_job() -> None:
    repo = _repo_with_pool()
    job = _build_run_job()
    await repo.enqueue_run_job(job)
    await repo.claim_next_run_job()

    await repo.fail_run_job(job.artifact_id)

    assert repo._jobs[job.artifact_id].status is RunJobStatus.FAILED


@pytest.mark.asyncio
async def test_cancel_job() -> None:
    repo = _repo_with_pool()
    job = _build_run_job()
    await repo.enqueue_run_job(job)

    await repo.cancel_run_job(job.artifact_id)

    assert repo._jobs[job.artifact_id].status is RunJobStatus.CANCELED


@pytest.mark.asyncio
async def test_requeue_job() -> None:
    repo = _repo_with_pool()
    job = _build_run_job()
    await repo.enqueue_run_job(job)
    await repo.claim_next_run_job()

    requeued = await repo.requeue_run_job(job.artifact_id)

    assert requeued is not None
    assert requeued.status is RunJobStatus.QUEUED


@pytest.mark.asyncio
async def test_requeue_missing_job_returns_none() -> None:
    repo = _repo_with_pool()
    assert await repo.requeue_run_job(uuid4()) is None


@pytest.mark.asyncio
async def test_reset_inflight_jobs() -> None:
    repo = _repo_with_pool()
    job = _build_run_job()
    await repo.enqueue_run_job(job)
    await repo.claim_next_run_job()

    count = await repo.reset_inflight_jobs()

    assert count == 1
    assert repo._jobs[job.artifact_id].status is RunJobStatus.QUEUED


# ---------------------------------------------------------------------------
# Graph checkpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_graph_checkpoint() -> None:
    repo = _repo_with_pool()
    aid = uuid4()
    checkpoint = GraphCheckpoint(
        artifact_id=aid,
        state=GraphRunState(
            artifact_id=aid,
            input_data=RunInput(source_type=SourceType.TEXT, source_label="draft", text="t"),
        ),
    )

    saved = await repo.save_graph_checkpoint(checkpoint)
    fetched = await repo.get_graph_checkpoint(aid)

    assert fetched is not None
    assert fetched.artifact_id == aid
    assert saved is not fetched


@pytest.mark.asyncio
async def test_get_checkpoint_falls_back_to_postgres() -> None:
    aid = uuid4()
    checkpoint = GraphCheckpoint(
        artifact_id=aid,
        state=GraphRunState(
            artifact_id=aid,
            input_data=RunInput(source_type=SourceType.TEXT, source_label="d", text="t"),
        ),
    )
    payload = checkpoint.model_dump(mode="json")
    cursor = FakeCursor(rows=[{"payload": payload}])
    pool = FakePool(FakeConnection(cursor))
    repo = _repo_with_pool(pool)

    fetched = await repo.get_graph_checkpoint(aid)

    assert fetched is not None
    assert fetched.artifact_id == aid


@pytest.mark.asyncio
async def test_delete_graph_checkpoint() -> None:
    repo = _repo_with_pool()
    aid = uuid4()
    checkpoint = GraphCheckpoint(
        artifact_id=aid,
        state=GraphRunState(
            artifact_id=aid,
            input_data=RunInput(source_type=SourceType.TEXT, source_label="d", text="t"),
        ),
    )
    await repo.save_graph_checkpoint(checkpoint)

    await repo.delete_graph_checkpoint(aid)

    assert aid not in repo._graph_checkpoints


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_check_healthy() -> None:
    cursor = FakeCursor(rows=[{"?column?": 1}])
    pool = FakePool(FakeConnection(cursor))
    repo = _repo_with_pool(pool)

    assert await repo.readiness_check() is True


@pytest.mark.asyncio
async def test_readiness_check_unreachable() -> None:
    repo = PostgresRunRepository("postgres://test:test@localhost/test")
    repo._pool = None  # noqa: SLF001

    assert await repo.readiness_check() is False
