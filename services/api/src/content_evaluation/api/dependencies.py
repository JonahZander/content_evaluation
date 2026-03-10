"""Dependency builders for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from content_evaluation.config import Settings, get_settings
from content_evaluation.domain.models import ReadinessReport
from content_evaluation.logging import get_logger
from content_evaluation.providers.extraction.client import TrafilaturaExtractionProvider
from content_evaluation.providers.interfaces.analysis import AnalysisProvider
from content_evaluation.providers.interfaces.extraction import ContentExtractionProvider
from content_evaluation.providers.interfaces.search import SimilaritySearchProvider
from content_evaluation.providers.mock.providers import (
    MockAnalysisProvider,
    MockContentExtractionProvider,
    MockSimilaritySearchProvider,
)
from content_evaluation.providers.openai.client import OpenAIAnalysisProvider
from content_evaluation.providers.tavily.client import TavilySearchProvider
from content_evaluation.repositories.base import RunRepository
from content_evaluation.repositories.in_memory import InMemoryRunRepository
from content_evaluation.repositories.postgres import PostgresRunRepository
from content_evaluation.services.comments import CommentService
from content_evaluation.services.orchestration import RunOrchestrator
from content_evaluation.services.worker import RunWorker


@dataclass(slots=True)
class ProviderHealth:
    """Describe the provider configuration for runtime checks."""

    analysis_provider: AnalysisProvider
    search_provider: SimilaritySearchProvider
    extraction_provider: ContentExtractionProvider
    providers_ready: bool


class AppServices:
    """Store long-lived service instances."""

    def __init__(self, settings: Settings) -> None:
        """Build repositories and providers for the app."""

        self.settings = settings
        self.logger = get_logger("content_evaluation.app")
        self.repository = self._build_repository(settings)
        provider_health = self._build_providers(settings)
        self.orchestrator = RunOrchestrator(
            self.repository,
            provider_health.analysis_provider,
            provider_health.search_provider,
            provider_health.extraction_provider,
            settings.runtime_mode,
            settings.persistent_storage_enabled,
        )
        self.comments = CommentService(self.repository, settings.reviewer_name)
        self.worker = RunWorker(self.repository, self.orchestrator, settings)
        self.providers_ready = provider_health.providers_ready

    async def start(self) -> None:
        """Start long-lived workers."""

        await self.worker.start()

    async def stop(self) -> None:
        """Stop long-lived workers."""

        await self.worker.stop()

    async def readiness_report(self) -> ReadinessReport:
        """Build one readiness report for the API."""

        database_ready = await self.repository.readiness_check()
        status = "ok" if database_ready and self.providers_ready else "degraded"
        return ReadinessReport(
            status=status,
            app_env=self.settings.app_env,
            processing_mode=self.settings.runtime_mode,
            persistent_storage=self.settings.persistent_storage_enabled,
            database_ready=database_ready,
            providers_ready=self.providers_ready,
        )

    @staticmethod
    def _build_repository(settings: Settings) -> RunRepository:
        """Build the configured repository."""

        if settings.database_url:
            return PostgresRunRepository(settings.database_url)
        return InMemoryRunRepository()

    @staticmethod
    def _build_providers(settings: Settings) -> ProviderHealth:
        """Build provider instances and readiness metadata."""

        if settings.runtime_mode.value == "live":
            return ProviderHealth(
                analysis_provider=OpenAIAnalysisProvider(
                    settings.openai_api_key or "",
                    timeout_seconds=settings.provider_timeout_seconds,
                ),
                search_provider=TavilySearchProvider(
                    settings.tavily_api_key or "",
                    timeout_seconds=settings.provider_timeout_seconds,
                ),
                extraction_provider=TrafilaturaExtractionProvider(
                    timeout_seconds=settings.request_timeout_seconds,
                ),
                providers_ready=True,
            )
        return ProviderHealth(
            analysis_provider=MockAnalysisProvider(),
            search_provider=MockSimilaritySearchProvider(),
            extraction_provider=MockContentExtractionProvider(),
            providers_ready=settings.app_env != "production",
        )


def get_services(request: Request) -> AppServices:
    """Return the app services from FastAPI state."""

    return request.app.state.services


def get_comment_service(request: Request) -> CommentService:
    """Return the comment service from FastAPI state."""

    return request.app.state.services.comments


def get_run_repository(request: Request) -> RunRepository:
    """Return the repository from FastAPI state."""

    return request.app.state.services.repository


def build_services() -> AppServices:
    """Create the long-lived service container."""

    return AppServices(get_settings())
