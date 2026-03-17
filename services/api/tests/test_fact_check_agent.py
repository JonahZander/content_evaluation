"""Tests for the fact_check agent and related components."""

from typing import Protocol

import pytest

from content_evaluation.domain.models import (
    AgentCategory,
    ArtifactBlock,
    ArtifactBlockKind,
    ArtifactBlockOrigin,
    ProviderKind,
)
from content_evaluation.providers.interfaces.deep_research import DeepResearchProvider
from content_evaluation.providers.mock.providers import MockDeepResearchProvider
from content_evaluation.services.normalization import build_fact_check_brief


def test_fact_check_category_exists():
    assert AgentCategory.FACT_CHECK == "fact_check"


def test_deep_research_provider_kind_exists():
    assert ProviderKind.DEEP_RESEARCH == "deep_research"


def test_deep_research_provider_is_protocol():
    assert issubclass(DeepResearchProvider, Protocol)


def _block(text: str) -> ArtifactBlock:
    return ArtifactBlock(
        index=0,
        kind=ArtifactBlockKind.PARAGRAPH,
        origin=ArtifactBlockOrigin.SOURCE,
        text=text,
    )


def test_build_fact_check_brief_includes_title():
    brief = build_fact_check_brief("My Post", [_block("AI will replace all jobs.")])
    assert "My Post" in brief
    assert "AI will replace all jobs." in brief


def test_build_fact_check_brief_no_title():
    brief = build_fact_check_brief(None, [_block("Some claim.")])
    assert "Some claim." in brief


def test_build_fact_check_brief_limits_blocks():
    blocks = [_block(f"Block {i}") for i in range(20)]
    for i, b in enumerate(blocks):
        b.index = i
    brief = build_fact_check_brief("T", blocks)
    assert "Block 9" in brief
    assert "Block 10" not in brief


@pytest.mark.asyncio
async def test_mock_provider_returns_valid_findings():
    result = await MockDeepResearchProvider().fact_check("brief", "Some article text.")
    assert isinstance(result["findings"], list)
    assert len(result["findings"]) >= 1
    f = result["findings"][0]
    for key in ("excerpt", "rationale", "confidence", "suggestion"):
        assert key in f
    assert 0.0 <= f["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_mock_provider_returns_summary_and_sources():
    result = await MockDeepResearchProvider().fact_check("brief", "text")
    assert isinstance(result["summary"], str)
    assert isinstance(result["metadata"]["sources"], list)


from content_evaluation.agents.registry import get_agent_definition, load_instruction_text
from content_evaluation.domain.models import AgentExecutionMode


def test_fact_check_agent_is_registered():
    defn = get_agent_definition("fact_check")
    assert defn.provider_kind is ProviderKind.DEEP_RESEARCH
    assert defn.execution_mode is AgentExecutionMode.MULTI_STEP
    assert defn.depends_on == ()
    assert defn.default_enabled is False


def test_fact_check_instruction_file_loads():
    defn = get_agent_definition("fact_check")
    text = load_instruction_text(defn)
    assert len(text) > 50


@pytest.mark.asyncio
async def test_mock_deep_research_provider_returns_usage() -> None:
    """MockDeepResearchProvider must include metadata.usage for UI display."""
    provider = MockDeepResearchProvider()
    result = await provider.fact_check("brief", "article text")
    meta = result.get("metadata", {})
    assert isinstance(meta, dict), "metadata must be a dict"
    usage = meta.get("usage")
    assert isinstance(usage, dict), "metadata.usage must be a dict"
    assert "input_tokens" in usage
    assert "output_tokens" in usage
    assert "total_tokens" in usage


@pytest.mark.asyncio
async def test_live_deep_research_provider_attaches_usage_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    """LiveDeepResearchProvider must pass a UsageMetadataCallbackHandler in config['callbacks']."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler

    import content_evaluation.providers.deep_research.provider as dr_module
    from content_evaluation.config import Settings
    from content_evaluation.providers.deep_research.provider import LiveDeepResearchProvider

    captured: list[dict] = []

    class FakeGraph:
        async def ainvoke(self, input_: object, config: dict) -> dict:
            captured.append(config)
            return {"final_report": '{"findings": [], "summary": "ok", "metadata": {}}'}

    class FakeBuilder:
        def compile(self, **_: object) -> FakeGraph:
            return FakeGraph()

    monkeypatch.setattr(dr_module, "deep_researcher_builder", FakeBuilder())

    prov = LiveDeepResearchProvider(Settings(openai_api_key="key", tavily_api_key="key"))
    await prov.fact_check("brief", "text")

    assert len(captured) == 1, "ainvoke was not called"
    callbacks = captured[0].get("callbacks", [])
    assert any(
        isinstance(cb, UsageMetadataCallbackHandler) for cb in callbacks
    ), "UsageMetadataCallbackHandler not found in config['callbacks']"
