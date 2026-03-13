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
