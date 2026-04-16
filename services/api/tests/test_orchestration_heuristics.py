"""Unit tests for orchestration heuristics."""

from __future__ import annotations

from content_evaluation.domain.models import (
    ArtifactBlock,
    ArtifactBlockKind,
    ArtifactBlockOrigin,
    ArtifactDocument,
    SourceType,
)
from content_evaluation.services.orchestration import _guess_article_format


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
