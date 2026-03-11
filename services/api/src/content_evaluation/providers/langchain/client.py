"""LangChain-backed structured analysis provider."""

from __future__ import annotations

from typing import Any, cast

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from content_evaluation.config import Settings
from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import (
    AnalysisProviderFamily,
    ArtifactBlock,
    ProviderRoute,
)


class _StructuredFinding(BaseModel):
    """Validate one structured finding returned by a chat model."""

    excerpt: str
    rationale: str
    confidence: float
    suggestion: str | None = None


class _StructuredAgentResponse(BaseModel):
    """Validate the common response envelope returned by analysis agents."""

    findings: list[_StructuredFinding] = Field(default_factory=list)
    summary: str | None = None


class LangChainAnalysisProvider:
    """Call supported chat models through LangChain and return structured results."""

    def __init__(self, settings: Settings) -> None:
        """Store runtime settings for route resolution."""

        self._settings = settings

    def resolve_model_name(self, route: ProviderRoute | None = None) -> str:
        """Return the resolved model name for one analysis request."""

        resolved = self._resolve_route(route)
        return resolved.model_name

    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
        route: ProviderRoute | None = None,
    ) -> dict[str, object]:
        """Run one structured analysis request through the routed chat model."""

        resolved_route = self._resolve_route(route)
        runnable = self._build_runnable(resolved_route)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a structured editorial analysis agent. "
                    "Return structured findings only and stay within the requested schema.",
                ),
                (
                    "human",
                    "{request}",
                ),
            ]
        )
        request = self._build_prompt(agent_id, instruction, title, blocks, context or {})

        try:
            response = await (prompt | runnable).ainvoke({"request": request})
        except Exception as error:  # pragma: no cover - framework exception types vary
            raise ProviderError(f"LangChain analysis request failed: {error}") from error

        parsed = response.model_dump(mode="json")
        findings = parsed.get("findings", [])
        if not isinstance(findings, list):
            raise ProviderError("Structured analysis response had an invalid findings shape")
        return parsed

    def _build_runnable(self, route: ProviderRoute) -> Any:
        """Return one structured-output runnable for the requested route."""

        model = self._build_chat_model(route)
        return model.with_structured_output(_StructuredAgentResponse)

    def _build_chat_model(self, route: ProviderRoute) -> Any:
        """Construct one chat model instance for the requested provider family."""
        if route.family is AnalysisProviderFamily.OPENAI:
            if self._settings.openai_api_key is None:
                raise ProviderError("OpenAI route selected without CONTENT_EVAL_OPENAI_API_KEY")
            return cast(
                Any,
                ChatOpenAI(
                    api_key=SecretStr(self._settings.openai_api_key),
                    model=route.model_name,
                    temperature=route.temperature,
                    timeout=route.timeout_seconds,
                    max_retries=route.max_retries,
                ),
            )
        if route.family is AnalysisProviderFamily.ANTHROPIC:
            if self._settings.anthropic_api_key is None:
                raise ProviderError("Anthropic route selected without CONTENT_EVAL_ANTHROPIC_API_KEY")
            return cast(
                Any,
                ChatAnthropic(
                    api_key=SecretStr(self._settings.anthropic_api_key),
                    model_name=route.model_name,
                    temperature=route.temperature,
                    timeout=route.timeout_seconds,
                    max_retries=route.max_retries,
                    stop=None,
                ),
            )
        if route.family is AnalysisProviderFamily.GEMINI:
            if self._settings.gemini_api_key is None:
                raise ProviderError("Gemini route selected without CONTENT_EVAL_GEMINI_API_KEY")
            return cast(
                Any,
                ChatGoogleGenerativeAI(
                    google_api_key=SecretStr(self._settings.gemini_api_key),
                    model=route.model_name,
                    temperature=route.temperature,
                    timeout=route.timeout_seconds,
                    max_retries=route.max_retries,
                ),
            )
        raise ProviderError(f"Unsupported analysis provider family: {route.family}")

    def _resolve_route(self, route: ProviderRoute | None) -> ProviderRoute:
        """Resolve a route override against global settings defaults."""

        if route is not None:
            return route
        default_family = self._settings.analysis_provider_family
        return ProviderRoute(
            family=default_family,
            model_name=self._default_model_name(default_family),
            temperature=self._settings.analysis_temperature,
            timeout_seconds=self._settings.provider_timeout_seconds,
            max_retries=self._settings.analysis_max_retries,
        )

    def _default_model_name(self, family: AnalysisProviderFamily) -> str:
        """Return the default model name for one provider family."""

        if family is AnalysisProviderFamily.OPENAI:
            return self._settings.openai_model_name
        if family is AnalysisProviderFamily.ANTHROPIC:
            return self._settings.anthropic_model_name
        if family is AnalysisProviderFamily.GEMINI:
            return self._settings.gemini_model_name
        raise ProviderError(f"Unsupported analysis provider family: {family}")

    @staticmethod
    def _build_prompt(
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object],
    ) -> str:
        """Build the prompt body for one analysis request."""

        joined_blocks = "\n\n".join(f"[{block.id}] {block.text}" for block in blocks)
        return (
            f"Agent: {agent_id}\n"
            f"Title: {title}\n\n"
            f"Instruction:\n{instruction}\n\n"
            f"Upstream context:\n{context}\n\n"
            "Return structured findings only.\n\n"
            f"Document:\n{joined_blocks}"
        )
