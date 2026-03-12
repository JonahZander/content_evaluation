"""LangChain provider tests."""

from __future__ import annotations

import warnings

import pytest
from langchain_core.runnables import RunnableLambda

from content_evaluation.agents.registry import get_agent_definition, load_instruction_text
from content_evaluation.config import Settings
from content_evaluation.domain.models import AnalysisProviderFamily, ArtifactBlock, ProviderRoute
from content_evaluation.providers.langchain.client import LangChainAnalysisProvider


class _StructuredResponse:
    """Return one deterministic structured response object."""

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        """Return the serialized structured response."""

        del mode
        return {
            "findings": [
                {
                    "excerpt": "Alpha",
                    "rationale": "Reason",
                    "confidence": 0.8,
                    "suggestion": "Trim",
                }
            ],
            "summary": "Structured summary",
        }


class _ParsedStructuredResponse:
    """Return one wrapper that mimics a parsed provider payload."""

    def __init__(self) -> None:
        self.parsed = _StructuredResponse()


@pytest.mark.asyncio
async def test_langchain_provider_parses_structured_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return structured findings through the LangChain provider contract."""

    provider = LangChainAnalysisProvider(
        Settings(openai_api_key="openai-key", tavily_api_key="tavily-key")
    )
    monkeypatch.setattr(provider, "_build_runnable", lambda route: RunnableLambda(lambda _: _StructuredResponse()))

    findings = await provider.analyze(
        "value",
        "Analyze value",
        "Title",
        [ArtifactBlock(index=0, text="Alpha text")],
    )

    findings_payload = findings["findings"]
    assert isinstance(findings_payload, list)
    assert findings_payload[0]["rationale"] == "Reason"


def test_langchain_provider_resolves_override_route() -> None:
    """Resolve the configured model name from one override route."""

    provider = LangChainAnalysisProvider(
        Settings(
            openai_api_key="openai-key",
            tavily_api_key="tavily-key",
            analysis_provider_family=AnalysisProviderFamily.OPENAI,
            openai_model_name="gpt-4.1-mini",
        )
    )

    assert (
        provider.resolve_model_name(
            ProviderRoute(
                family=AnalysisProviderFamily.GEMINI,
                model_name="gemini-2.0-flash",
            )
        )
        == "gemini-2.0-flash"
    )


@pytest.mark.asyncio
async def test_langchain_provider_normalizes_parsed_wrapper_without_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist plain JSON even when the provider returns a parsed wrapper object."""

    provider = LangChainAnalysisProvider(
        Settings(openai_api_key="openai-key", tavily_api_key="tavily-key")
    )
    monkeypatch.setattr(provider, "_build_runnable", lambda route: RunnableLambda(lambda _: _ParsedStructuredResponse()))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("error")
        payload = await provider.analyze(
            "value",
            "Analyze value",
            "Title",
            [ArtifactBlock(index=0, text="Alpha text")],
        )

    assert payload["summary"] == "Structured summary"
    assert caught == []


def test_agent_instructions_define_exact_excerpt_and_ellipsis_rules() -> None:
    """Keep excerpt and ellipsis guidance explicit in finding-producing agent prompts."""

    for agent_id in ("editorial", "value", "audience", "ai_likelihood", "synthesis"):
        instruction = load_instruction_text(get_agent_definition(agent_id))
        assert "word for word" in instruction
        assert "Use ellipses only" in instruction
        assert "more than 3 paragraphs" in instruction
