"""Run worker retry behavior tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from content_evaluation.config import Settings
from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import RunInput, SourceType
from content_evaluation.services.worker import RunWorker


def _build_settings() -> Settings:
    """Build settings tuned for direct worker unit tests."""

    return Settings(
        app_env="test",
        analysis_provider_family="mock",
        worker_max_attempts=2,
        worker_poll_interval_seconds=0.01,
        worker_max_concurrent_runs=1,
        openai_api_key=None,
        anthropic_api_key=None,
        gemini_api_key=None,
        tavily_api_key=None,
    )


def _build_worker() -> tuple[RunWorker, SimpleNamespace]:
    """Build one worker with async mocks for its collaborators."""

    repository = SimpleNamespace(
        fail_run_job=AsyncMock(),
        requeue_run_job=AsyncMock(),
        cancel_run_job=AsyncMock(),
        delete_graph_checkpoint=AsyncMock(),
    )
    orchestrator = SimpleNamespace(process_run=AsyncMock())
    worker = RunWorker(repository, orchestrator, _build_settings())
    return worker, repository


def _build_job(attempts: int = 1):
    """Build one queued job for the worker tests."""

    from content_evaluation.domain.models import RunJob

    return RunJob(
        artifact_id=uuid4(),
        input_data=RunInput(source_type=SourceType.TEXT, source_label="draft", text="Draft"),
        attempts=attempts,
    )


@pytest.mark.asyncio
async def test_retriable_provider_error_requeues_while_attempts_remain() -> None:
    """Retry provider failures that are explicitly marked retriable."""

    worker, repository = _build_worker()
    job = _build_job(attempts=1)
    error = ProviderError("temporary provider failure", retriable=True, provider_name="openai")
    worker._orchestrator.process_run.side_effect = error  # noqa: SLF001

    await worker._process_job(job)  # noqa: SLF001

    repository.requeue_run_job.assert_awaited_once_with(job.artifact_id)
    repository.fail_run_job.assert_not_awaited()
    repository.cancel_run_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_retriable_provider_error_fails_immediately() -> None:
    """Fail provider failures that are not explicitly retriable."""

    worker, repository = _build_worker()
    job = _build_job(attempts=1)
    error = ProviderError("permanent provider failure", retriable=False, provider_name="openai")
    worker._orchestrator.process_run.side_effect = error  # noqa: SLF001

    await worker._process_job(job)  # noqa: SLF001

    repository.fail_run_job.assert_awaited_once_with(job.artifact_id)
    repository.requeue_run_job.assert_not_awaited()
    repository.cancel_run_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_retriable_provider_error_fails_when_attempts_are_exhausted() -> None:
    """Stop retrying retriable provider failures once attempts are exhausted."""

    worker, repository = _build_worker()
    job = _build_job(attempts=2)
    error = ProviderError("temporary provider failure", retriable=True, provider_name="openai")
    worker._orchestrator.process_run.side_effect = error  # noqa: SLF001

    await worker._process_job(job)  # noqa: SLF001

    repository.fail_run_job.assert_awaited_once_with(job.artifact_id)
    repository.requeue_run_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_exception_requeues_while_attempts_remain() -> None:
    """Keep bounded retries for unexpected exceptions."""

    worker, repository = _build_worker()
    job = _build_job(attempts=1)
    worker._orchestrator.process_run.side_effect = RuntimeError("boom")  # noqa: SLF001

    await worker._process_job(job)  # noqa: SLF001

    repository.requeue_run_job.assert_awaited_once_with(job.artifact_id)
    repository.fail_run_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_exception_fails_when_attempts_are_exhausted() -> None:
    """Stop retrying unexpected errors after the configured maximum."""

    worker, repository = _build_worker()
    job = _build_job(attempts=2)
    worker._orchestrator.process_run.side_effect = RuntimeError("boom")  # noqa: SLF001

    await worker._process_job(job)  # noqa: SLF001

    repository.fail_run_job.assert_awaited_once_with(job.artifact_id)
    repository.requeue_run_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_run_is_not_requeued() -> None:
    """Canceled runs should be marked canceled rather than requeued."""

    worker, repository = _build_worker()
    job = _build_job(attempts=1)
    worker._orchestrator.process_run.side_effect = asyncio.CancelledError()  # noqa: SLF001

    await worker._process_job(job)  # noqa: SLF001

    repository.cancel_run_job.assert_awaited_once_with(job.artifact_id)
    repository.delete_graph_checkpoint.assert_awaited_once_with(job.artifact_id)
    repository.requeue_run_job.assert_not_awaited()
    repository.fail_run_job.assert_not_awaited()
