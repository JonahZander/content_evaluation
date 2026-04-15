"""Durable run worker with bounded concurrency."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from uuid import UUID

from content_evaluation.config import Settings
from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.logging import get_logger
from content_evaluation.repositories.base import RunRepository
from content_evaluation.services.orchestration import RunOrchestrator


class RunWorker:
    """Poll queued jobs and execute analysis runs with bounded concurrency."""

    def __init__(self, repository: RunRepository, orchestrator: RunOrchestrator, settings: Settings) -> None:
        self._repository = repository
        self._orchestrator = orchestrator
        self._settings = settings
        self._logger = get_logger("content_evaluation.worker")
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._active_runs: dict[UUID, asyncio.Task[None]] = {}

    async def start(self) -> None:
        """Start the worker loop."""

        await self._repository.reset_inflight_jobs()
        self._task = asyncio.create_task(self._run(), name="content-evaluation-worker")

    async def stop(self) -> None:
        """Stop the worker loop and drain in-flight tasks."""

        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._active_runs:
            await asyncio.gather(*self._active_runs.values(), return_exceptions=True)

    async def _run(self) -> None:
        """Poll and execute queued jobs with bounded concurrency."""

        sem = asyncio.Semaphore(self._settings.worker_max_concurrent_runs)

        while not self._stop_event.is_set():
            if sem.locked():
                await asyncio.sleep(self._settings.worker_poll_interval_seconds)
                continue

            job = await self._repository.claim_next_run_job()
            if job is None:
                await asyncio.sleep(self._settings.worker_poll_interval_seconds)
                continue

            self._logger.info("worker claimed artifact_id=%s attempt=%s", job.artifact_id, job.attempts)
            task = asyncio.create_task(self._process_job(job, sem), name=f"run-{job.artifact_id}")
            self._active_runs[job.artifact_id] = task

    async def _process_job(self, job: object, sem: asyncio.Semaphore | None = None) -> None:
        """Run one claimed job and apply the retry policy for failures."""

        from content_evaluation.domain.models import RunJob

        assert isinstance(job, RunJob)
        semaphore = sem or asyncio.Semaphore(self._settings.worker_max_concurrent_runs)
        async with semaphore:
            try:
                await self._orchestrator.process_run(
                    job.artifact_id,
                    job.input_data,
                    attempt=job.attempts,
                    max_attempts=self._settings.worker_max_attempts,
                )
            except asyncio.CancelledError:
                await self._repository.cancel_run_job(job.artifact_id)
                await self._repository.delete_graph_checkpoint(job.artifact_id)
                self._logger.info("worker canceled artifact_id=%s", job.artifact_id)
            except ProviderError as error:
                if error.retriable and job.attempts < self._settings.worker_max_attempts:
                    await self._repository.requeue_run_job(job.artifact_id)
                    self._logger.exception(
                        "worker requeued artifact_id=%s attempt=%s retriable=%s",
                        job.artifact_id,
                        job.attempts,
                        error.retriable,
                    )
                else:
                    await self._repository.fail_run_job(job.artifact_id)
                    self._logger.exception(
                        "worker failed artifact_id=%s attempts=%s retriable=%s",
                        job.artifact_id,
                        job.attempts,
                        error.retriable,
                    )
            except Exception:
                if job.attempts < self._settings.worker_max_attempts:
                    await self._repository.requeue_run_job(job.artifact_id)
                    self._logger.exception("worker requeued artifact_id=%s attempt=%s", job.artifact_id, job.attempts)
                else:
                    await self._repository.fail_run_job(job.artifact_id)
                    self._logger.exception("worker failed artifact_id=%s attempts=%s", job.artifact_id, job.attempts)
            else:
                await self._repository.complete_run_job(job.artifact_id)
                self._logger.info("worker completed artifact_id=%s", job.artifact_id)
            finally:
                self._active_runs.pop(job.artifact_id, None)

    async def cancel_run(self, artifact_id: UUID) -> bool:
        """Cancel one actively running artifact task if present."""

        run_task = self._active_runs.get(artifact_id)
        if run_task is None or run_task.done():
            return False
        run_task.cancel()
        with suppress(asyncio.CancelledError):
            await run_task
        return True
