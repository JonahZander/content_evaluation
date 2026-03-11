"""LangChain provider tests."""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda

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
