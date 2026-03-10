"""Dependency builders for FastAPI."""

from __future__ import annotations

from fastapi import Request

from content_evaluation.config import Settings, get_settings
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


class AppServices:
    """Store long-lived service instances."""

    def __init__(self, settings: Settings) -> None:
        """Build repositories and providers for the app."""

        self.settings = settings
        self.repository = self._build_repository(settings)
        analysis_provider: AnalysisProvider
        search_provider: SimilaritySearchProvider
        extraction_provider: ContentExtractionProvider
        if settings.openai_api_key and settings.tavily_api_key:
            analysis_provider = OpenAIAnalysisProvider(settings.openai_api_key)
            search_provider = TavilySearchProvider(settings.tavily_api_key)
            extraction_provider = TrafilaturaExtractionProvider()
        else:
            analysis_provider = MockAnalysisProvider()
            search_provider = MockSimilaritySearchProvider()
            extraction_provider = MockContentExtractionProvider()
        self.orchestrator = RunOrchestrator(self.repository, analysis_provider, search_provider, extraction_provider)
        self.comments = CommentService(self.repository, settings.reviewer_name)

    @staticmethod
    def _build_repository(settings: Settings) -> RunRepository:
        """Build the configured repository."""

        if settings.database_url:
            return PostgresRunRepository(settings.database_url)
        return InMemoryRunRepository()


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
