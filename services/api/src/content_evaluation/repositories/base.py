"""Repository interfaces."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from content_evaluation.domain.models import AnalysisArtifact, GraphCheckpoint, RunJob


class RunRepository(Protocol):
    """Describe storage operations for artifacts and queued jobs."""

    async def create_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist a new artifact."""

    async def update_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        """Persist an updated artifact snapshot."""

    async def get_artifact(self, artifact_id: UUID) -> AnalysisArtifact | None:
        """Return one artifact snapshot."""

    async def enqueue_run_job(self, job: RunJob) -> RunJob:
        """Persist a queued job."""

    async def claim_next_run_job(self) -> RunJob | None:
        """Claim the next queued job for worker processing."""

    async def complete_run_job(self, artifact_id: UUID) -> None:
        """Mark one queued job as completed."""

    async def fail_run_job(self, artifact_id: UUID) -> None:
        """Mark one queued job as failed."""

    async def cancel_run_job(self, artifact_id: UUID) -> None:
        """Mark one queued or running job as canceled."""

    async def requeue_run_job(self, artifact_id: UUID) -> RunJob | None:
        """Return a failed/running job back to the queue."""

    async def reset_inflight_jobs(self) -> int:
        """Reset running jobs when the worker starts."""

    async def readiness_check(self) -> bool:
        """Return whether the storage backend is ready."""

    async def save_graph_checkpoint(self, checkpoint: GraphCheckpoint) -> GraphCheckpoint:
        """Persist the latest graph checkpoint for one artifact."""

    async def get_graph_checkpoint(self, artifact_id: UUID) -> GraphCheckpoint | None:
        """Return the latest graph checkpoint for one artifact."""

    async def delete_graph_checkpoint(self, artifact_id: UUID) -> None:
        """Remove the stored graph checkpoint for one artifact."""
