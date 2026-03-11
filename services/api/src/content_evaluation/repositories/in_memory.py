"""In-memory repository implementation."""

from __future__ import annotations

from copy import deepcopy
from uuid import UUID

from content_evaluation.domain.exceptions import NotFoundError
from content_evaluation.domain.models import AnalysisArtifact, GraphCheckpoint, RunJob, RunJobStatus, now_utc


class InMemoryRunRepository:
    """Persist artifact state in memory for tests and local fallback."""

    def __init__(self) -> None:
        """Initialize the in-memory store."""

        self._artifacts: dict[UUID, AnalysisArtifact] = {}
        self._jobs: dict[UUID, RunJob] = {}
        self._graph_checkpoints: dict[UUID, GraphCheckpoint] = {}

    async def create_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist a new artifact."""

        self._artifacts[artifact.artifact_id] = deepcopy(artifact)
        return deepcopy(artifact)

    async def update_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist an updated artifact snapshot."""

        if artifact.artifact_id not in self._artifacts:
            raise NotFoundError(f"Artifact {artifact.artifact_id} not found")
        artifact.updated_at = now_utc()
        self._artifacts[artifact.artifact_id] = deepcopy(artifact)
        return deepcopy(artifact)

    async def get_artifact(self, artifact_id: UUID) -> AnalysisArtifact | None:
        """Return one artifact snapshot."""

        artifact = self._artifacts.get(artifact_id)
        return deepcopy(artifact) if artifact is not None else None

    async def enqueue_run_job(self, job: RunJob) -> RunJob:
        """Persist a queued job."""

        self._jobs[job.artifact_id] = deepcopy(job)
        return deepcopy(job)

    async def claim_next_run_job(self) -> RunJob | None:
        """Claim the next queued job."""

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
        return deepcopy(job)

    async def complete_run_job(self, artifact_id: UUID) -> None:
        """Mark one job as completed."""

        job = self._jobs.get(artifact_id)
        if job is not None and job.status is not RunJobStatus.CANCELED:
            job.status = RunJobStatus.COMPLETED
            job.updated_at = now_utc()

    async def fail_run_job(self, artifact_id: UUID) -> None:
        """Mark one job as failed."""

        job = self._require_job(artifact_id)
        if job.status is RunJobStatus.CANCELED:
            return
        job.status = RunJobStatus.FAILED
        job.updated_at = now_utc()

    async def cancel_run_job(self, artifact_id: UUID) -> None:
        """Mark one job as canceled."""

        job = self._jobs.get(artifact_id)
        if job is not None:
            job.status = RunJobStatus.CANCELED
            job.updated_at = now_utc()

    async def requeue_run_job(self, artifact_id: UUID) -> RunJob | None:
        """Move one job back to queued state."""

        job = self._jobs.get(artifact_id)
        if job is None:
            return None
        if job.status is RunJobStatus.CANCELED:
            return deepcopy(job)
        job.status = RunJobStatus.QUEUED
        job.updated_at = now_utc()
        return deepcopy(job)

    async def reset_inflight_jobs(self) -> int:
        """Return running jobs to the queue."""

        reset_count = 0
        for job in self._jobs.values():
            if job.status is RunJobStatus.RUNNING:
                job.status = RunJobStatus.QUEUED
                job.updated_at = now_utc()
                reset_count += 1
        return reset_count

    async def readiness_check(self) -> bool:
        """Return storage readiness for the in-memory repository."""

        return True

    async def save_graph_checkpoint(self, checkpoint: GraphCheckpoint) -> GraphCheckpoint:
        """Persist one graph checkpoint in memory."""

        checkpoint.updated_at = now_utc()
        self._graph_checkpoints[checkpoint.artifact_id] = deepcopy(checkpoint)
        return deepcopy(checkpoint)

    async def get_graph_checkpoint(self, artifact_id: UUID) -> GraphCheckpoint | None:
        """Return one graph checkpoint snapshot."""

        checkpoint = self._graph_checkpoints.get(artifact_id)
        return deepcopy(checkpoint) if checkpoint is not None else None

    async def delete_graph_checkpoint(self, artifact_id: UUID) -> None:
        """Delete one persisted graph checkpoint."""

        self._graph_checkpoints.pop(artifact_id, None)

    def _require_job(self, artifact_id: UUID) -> RunJob:
        """Return a queued job or raise."""

        job = self._jobs.get(artifact_id)
        if job is None:
            raise NotFoundError(f"Run job {artifact_id} not found")
        return job
