"""Durable run worker."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from content_evaluation.config import Settings
from content_evaluation.logging import get_logger
from content_evaluation.repositories.base import RunRepository
from content_evaluation.services.orchestration import RunOrchestrator


class RunWorker:
    """Poll queued jobs and execute analysis runs."""

    def __init__(self, repository: RunRepository, orchestrator: RunOrchestrator, settings: Settings) -> None:
        """Initialize the durable worker."""

        self._repository = repository
        self._orchestrator = orchestrator
        self._settings = settings
        self._logger = get_logger("content_evaluation.worker")
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the worker loop."""

        await self._repository.reset_inflight_jobs()
        self._task = asyncio.create_task(self._run(), name="content-evaluation-worker")

    async def stop(self) -> None:
        """Stop the worker loop."""

        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        """Poll and execute queued jobs."""

        while not self._stop_event.is_set():
            job = await self._repository.claim_next_run_job()
            if job is None:
                await asyncio.sleep(self._settings.worker_poll_interval_seconds)
                continue

            self._logger.info("worker claimed run_id=%s attempt=%s", job.run_id, job.attempts)
            try:
                await self._orchestrator.process_run(job.run_id, job.input_data)
            except Exception:
                if job.attempts < self._settings.worker_max_attempts:
                    await self._repository.requeue_run_job(job.run_id)
                    self._logger.exception("worker requeued run_id=%s attempt=%s", job.run_id, job.attempts)
                else:
                    await self._repository.fail_run_job(job.run_id)
                    self._logger.exception("worker failed run_id=%s attempts=%s", job.run_id, job.attempts)
            else:
                await self._repository.complete_run_job(job.run_id)
                self._logger.info("worker completed run_id=%s", job.run_id)
