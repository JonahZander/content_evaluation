"""Backward-compatible OpenAI analysis provider wrapper."""

from __future__ import annotations

from content_evaluation.config import Settings
from content_evaluation.domain.models import AnalysisProviderFamily, ArtifactBlock, ProviderRoute
from content_evaluation.providers.langchain.client import LangChainAnalysisProvider


class OpenAIAnalysisProvider:
    """Keep the historical OpenAI provider name while delegating to LangChain."""

    def __init__(self, api_key: str, *, model_name: str = "gpt-4.1-mini", timeout_seconds: float = 45.0) -> None:
        """Initialize a LangChain provider pinned to OpenAI."""

        self._route = ProviderRoute(
            family=AnalysisProviderFamily.OPENAI,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )
        self._provider = LangChainAnalysisProvider(
            Settings(
                openai_api_key=api_key,
                tavily_api_key="unused-for-provider-wrapper",
                analysis_provider_family=AnalysisProviderFamily.OPENAI,
                openai_model_name=model_name,
                provider_timeout_seconds=timeout_seconds,
            )
        )

    @property
    def model_name(self) -> str:
        """Expose the configured model name."""

        return self._route.model_name

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        """Request structured JSON through the OpenAI-backed LangChain route."""

        return await self._provider.analyze(
            agent_id,
            instruction,
            title,
            blocks,
            context,
            route=route or self._route,
        )

    def resolve_model_name(self, route: ProviderRoute | None = None) -> str:
        """Return the resolved OpenAI model name."""

        return self._provider.resolve_model_name(route or self._route)
