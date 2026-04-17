"""Unit tests for orchestration heuristics."""

from __future__ import annotations

from content_evaluation.domain.models import (
    AgentCategory,
    AgentFinding,
    AgentPlanStatus,
    ArtifactAgentResult,
    ArtifactBlock,
    ArtifactBlockKind,
    ArtifactBlockOrigin,
    ArtifactDocument,
    ArtifactPreviousDraftSnapshot,
    SourceType,
)
from content_evaluation.services.orchestration import (
    _format_prior_research_context,
    _guess_article_format,
)


def _block(
    text: str,
    *,
    index: int = 0,
    kind: ArtifactBlockKind = ArtifactBlockKind.PARAGRAPH,
    origin: ArtifactBlockOrigin = ArtifactBlockOrigin.SOURCE,
) -> ArtifactBlock:
    return ArtifactBlock(text=text, index=index, kind=kind, origin=origin)


def _doc(title: str, blocks: list[ArtifactBlock]) -> ArtifactDocument:
    indexed_blocks = [
        block.model_copy(update={"index": position})
        for position, block in enumerate(blocks)
    ]
    text = "\n\n".join(block.text for block in indexed_blocks)
    return ArtifactDocument(
        title=title,
        source_type=SourceType.TEXT,
        source_label="test",
        text=text,
        blocks=indexed_blocks,
    )


def test_first_person_voice_does_not_imply_case_study() -> None:
    doc = _doc(
        "Before You Publish an AI-Assisted Post",
        [
            _block("I think there are five questions worth asking before it goes live."),
            _block("1. Which claims would be embarrassing to get wrong?", kind=ArtifactBlockKind.HEADING),
            _block("Do not try to verify everything equally. We start with the claims that create real risk."),
            _block("2. Does the source actually support the sentence beside it?", kind=ArtifactBlockKind.HEADING),
            _block("A real link is not the same thing as support."),
        ],
    )

    assert _guess_article_format(doc) != "case_study"


def test_numbered_headings_are_detected_as_checklist() -> None:
    doc = _doc(
        "Before You Publish an AI-Assisted Post",
        [
            _block("Intro paragraph that sets up the list."),
            _block("1. First question", kind=ArtifactBlockKind.HEADING),
            _block("2. Second question", kind=ArtifactBlockKind.HEADING),
            _block("3. Third question", kind=ArtifactBlockKind.HEADING),
        ],
    )

    assert _guess_article_format(doc) == "checklist"


def test_question_headings_are_detected_as_checklist() -> None:
    doc = _doc(
        "Review prompts",
        [
            _block("Intro."),
            _block("Is the source current?", kind=ArtifactBlockKind.HEADING),
            _block("Does the claim match the linked evidence?", kind=ArtifactBlockKind.HEADING),
        ],
    )

    assert _guess_article_format(doc) == "checklist"


def test_case_study_requires_title_cue() -> None:
    doc = _doc(
        "Case Study: How X Did Y",
        [
            _block("We rebuilt our pipeline last year and here is what happened."),
        ],
    )

    assert _guess_article_format(doc) == "case_study"


def test_how_to_title_returns_tutorial() -> None:
    doc = _doc(
        "How to ship faster",
        [
            _block("Step one: plan."),
        ],
    )

    assert _guess_article_format(doc) == "tutorial"


def test_announcement_title_returns_announcement() -> None:
    doc = _doc(
        "Announcing Content Evaluation 2.0",
        [
            _block("Today we are launching the next version."),
        ],
    )

    assert _guess_article_format(doc) == "announcement"


def test_many_non_structured_headings_still_return_roundup() -> None:
    doc = _doc(
        "Industry trends",
        [
            _block("Intro."),
            _block("Trend one", kind=ArtifactBlockKind.HEADING),
            _block("Trend two", kind=ArtifactBlockKind.HEADING),
            _block("Trend three", kind=ArtifactBlockKind.HEADING),
            _block("Trend four", kind=ArtifactBlockKind.HEADING),
        ],
    )

    assert _guess_article_format(doc) == "roundup"


def test_plain_article_falls_through_to_article() -> None:
    doc = _doc(
        "Some thoughts on writing",
        [
            _block("Writing well is hard. I find it takes practice."),
        ],
    )

    assert _guess_article_format(doc) == "article"


def _minimal_document() -> ArtifactDocument:
    return _doc("Prior draft", [_block("Prior draft body text.")])


def test_format_prior_research_context_returns_none_without_snapshot() -> None:
    assert _format_prior_research_context(None) is None


def test_format_prior_research_context_returns_none_when_no_fact_check_results() -> None:
    snapshot = ArtifactPreviousDraftSnapshot(
        document_revision_id="rev-1",
        document=_minimal_document(),
        agent_results=[
            ArtifactAgentResult(
                agent_id="editorial",
                document_revision_id="rev-1",
                category=AgentCategory.EDITORIAL,
                status=AgentPlanStatus.COMPLETED,
            )
        ],
    )

    assert _format_prior_research_context(snapshot) is None


def test_format_prior_research_context_builds_dedup_block() -> None:
    finding = AgentFinding(
        category=AgentCategory.FACT_CHECK,
        agent_name="fact_check",
        anchor_ids=["anchor-1"],
        rationale="Supported by a reputable source.",
        confidence=0.9,
        model_name="test-model",
        metadata={"verdict": "supported", "excerpt": "A claim about X"},
    )
    snapshot = ArtifactPreviousDraftSnapshot(
        document_revision_id="rev-1",
        document=_minimal_document(),
        agent_results=[
            ArtifactAgentResult(
                agent_id="fact_check",
                document_revision_id="rev-1",
                category=AgentCategory.FACT_CHECK,
                status=AgentPlanStatus.COMPLETED,
                findings=[finding],
                metadata={
                    "overlap_items": [
                        {"title": "Survey", "url": "https://example.com/survey", "note": "n"}
                    ]
                },
            )
        ],
    )

    output = _format_prior_research_context(snapshot)

    assert output is not None
    assert "PREVIOUSLY INVESTIGATED" in output
    assert "https://example.com/survey" in output
    assert "SUPPORTED: A claim about X" in output
    assert "Use this only to avoid duplicate work" in output
