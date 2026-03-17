"""LangChain-backed structured analysis provider."""

from __future__ import annotations

from typing import Any, cast

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from openai import APITimeoutError
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
        self._model_cache: dict[tuple[AnalysisProviderFamily, str], Any] = {}

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

        handler = UsageMetadataCallbackHandler()
        try:
            response = await (prompt | runnable).ainvoke({"request": request}, config={"callbacks": [handler]})
        except Exception as error:  # pragma: no cover - framework exception types vary
            raise self._classify_provider_error(error) from error

        parsed = self._normalize_response(response)
        findings = parsed.get("findings", [])
        if not isinstance(findings, list):
            raise ProviderError(
                "Structured analysis response had an invalid findings shape",
                kind="invalid_response",
                provider_name=resolved_route.family.value,
            )
        usage = self._extract_usage_from_handler(handler)
        if usage is not None:
            parsed["usage"] = usage
        return parsed

    def _get_chat_model(self, route: ProviderRoute) -> Any:
        """Return a cached chat model for the given route, building one on first access."""

        key = (route.family, route.model_name)
        if key not in self._model_cache:
            self._model_cache[key] = self._build_chat_model(route)
        return self._model_cache[key]

    def _build_runnable(self, route: ProviderRoute) -> Any:
        """Return one structured-output runnable for the requested route."""

        model = self._get_chat_model(route)
        return model.with_structured_output(_StructuredAgentResponse)

    def _normalize_response(self, response: object) -> dict[str, object]:
        """Return one plain JSON payload regardless of the provider wrapper shape."""

        parsed_response = getattr(response, "parsed", response)
        if isinstance(parsed_response, _StructuredAgentResponse):
            return cast(dict[str, object], parsed_response.model_dump(mode="json"))
        if isinstance(parsed_response, dict):
            validated = _StructuredAgentResponse.model_validate(parsed_response)
            return cast(dict[str, object], validated.model_dump(mode="json"))
        if hasattr(parsed_response, "model_dump"):
            validated = _StructuredAgentResponse.model_validate(parsed_response.model_dump())
            return cast(dict[str, object], validated.model_dump(mode="json"))
        raise ProviderError("Structured analysis response had an unsupported payload shape", kind="invalid_response")

    def _classify_provider_error(self, error: Exception) -> ProviderError:
        """Map framework exceptions into stable provider errors."""

        provider_name = self._settings.analysis_provider_family.value
        if isinstance(error, (APITimeoutError, httpx.TimeoutException)):
            return ProviderError(
                f"LangChain analysis request failed: {error}",
                kind="timeout",
                retriable=True,
                provider_name=provider_name,
            )
        if isinstance(error, httpx.HTTPError):
            return ProviderError(
                f"LangChain analysis request failed: {error}",
                kind="network_error",
                retriable=True,
                provider_name=provider_name,
            )
        if isinstance(error, ProviderError):
            return error
        return ProviderError(
            f"LangChain analysis request failed: {error}",
            kind="provider_error",
            provider_name=provider_name,
        )

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
    def _extract_usage_from_handler(
        handler: UsageMetadataCallbackHandler,
    ) -> dict[str, int] | None:
        """Aggregate token counts from all model entries captured by the callback handler."""

        per_model = handler.usage_metadata  # {model_name: {token_counts}}
        if not per_model:
            return None
        input_t = sum(
            int(counts.get("input_tokens", 0))
            for counts in per_model.values()
            if isinstance(counts, dict)
        )
        output_t = sum(
            int(counts.get("output_tokens", 0))
            for counts in per_model.values()
            if isinstance(counts, dict)
        )
        return {
            "input_tokens": input_t,
            "output_tokens": output_t,
            "total_tokens": input_t + output_t,
        }

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
