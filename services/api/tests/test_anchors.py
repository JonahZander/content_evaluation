"""Anchor generation tests."""

from content_evaluation.domain.models import ArtifactBlock
from content_evaluation.services.anchors import create_anchor_from_excerpt


def test_create_anchor_from_excerpt_finds_offsets() -> None:
    """Locate an excerpt within a block."""

    block = ArtifactBlock(index=0, text="Editors should trim repeated paragraphs.")
    anchor = create_anchor_from_excerpt([block], "trim repeated")
    assert anchor is not None
    assert anchor.block_id == block.id
    assert anchor.start_offset == 15
    assert anchor.quote == "trim repeated"


def test_create_anchor_from_excerpt_collapses_whitespace() -> None:
    """Match excerpts even when line breaks and spaces differ."""

    block = ArtifactBlock(index=0, text="This isn’t an AI wrapper.\nThis isn’t an agent that gets replaced next year.")
    anchor = create_anchor_from_excerpt([block], "This isn’t an AI wrapper. This isn’t an agent that gets replaced next year.")

    assert anchor is not None
    assert anchor.block_id == block.id
    assert anchor.start_offset == 0
    assert anchor.end_offset == len(block.text)


def test_create_anchor_from_excerpt_handles_ellipses() -> None:
    """Match excerpts that were truncated in the middle."""

    text = (
        "In our Cade cost containment framework, we focus on five operational levers:\n"
        "1. Create a Unified Single Source of Truth\n"
        "2. Improve Intake\n"
        "3. Strengthen Engagement\n"
        "4. Scale Employer Acquisition in an AI-First World\n"
        "5. Scale the Provider Network Without Breaking Price Integrity"
    )
    block = ArtifactBlock(index=0, text=text)
    excerpt = (
        "In our Cade cost containment framework, we focus on five operational levers:\n"
        "1. Create a Unified Single Source of Truth\n"
        "…agement\n"
        "4. Scale Employer Acquisition in an AI-First World\n"
        "5. Scale the Provider Network Without Breaking Price Integrity"
    )

    anchor = create_anchor_from_excerpt([block], excerpt)

    assert anchor is not None
    assert anchor.block_id == block.id
    assert anchor.start_offset == 0
    assert "Scale the Provider Network Without Breaking Price Integrity" in block.text[anchor.start_offset : anchor.end_offset]


def test_create_anchor_from_excerpt_ignores_leading_ellipsis_fragment() -> None:
    """Ignore leading ellipses and start matching from the first real fragment."""

    block = ArtifactBlock(index=0, text="Alpha paragraph with important clause and supporting detail.")

    anchor = create_anchor_from_excerpt([block], "... important clause and supporting detail.")

    assert anchor is not None
    assert anchor.block_id == block.id
    assert block.text[anchor.start_offset : anchor.end_offset] == "important clause and supporting detail."


def test_create_anchor_from_excerpt_handles_middle_ellipsis_with_ordered_fragments() -> None:
    """Match ordered ellipsis fragments without collapsing them into one string."""

    block = ArtifactBlock(index=0, text="abc middle content 123 and then abc something else 456")

    anchor = create_anchor_from_excerpt([block], "abc ... 123")

    assert anchor is not None
    assert anchor.block_id == block.id
    assert block.text[anchor.start_offset : anchor.end_offset] == "abc middle content 123"


def test_create_anchor_from_excerpt_handles_trailing_ellipsis() -> None:
    """Match through the last real fragment when the excerpt ends with ellipsis."""

    block = ArtifactBlock(index=0, text="Start here and continue onward to the final claim.")

    anchor = create_anchor_from_excerpt([block], "Start here and continue ...")

    assert anchor is not None
    assert anchor.block_id == block.id
    assert block.text[anchor.start_offset : anchor.end_offset] == "Start here and continue"


def test_create_anchor_from_excerpt_returns_none_when_ellipsis_fragments_are_out_of_order() -> None:
    """Reject ellipsis excerpts that can only be satisfied out of order."""

    block = ArtifactBlock(index=0, text="123 arrives before abc in this sentence.")

    anchor = create_anchor_from_excerpt([block], "abc ... 123")

    assert anchor is None


def test_create_anchor_from_excerpt_returns_none_when_excerpt_spans_blocks() -> None:
    """Return no anchor when an excerpt cannot be mapped into a single block."""

    blocks = [
        ArtifactBlock(index=0, text="First paragraph."),
        ArtifactBlock(index=1, text="Second paragraph."),
    ]

    anchor = create_anchor_from_excerpt(blocks, "First paragraph.\n\nSecond paragraph.")

    assert anchor is None


def test_create_anchor_from_excerpt_returns_none_when_ellipsis_requires_multiple_blocks() -> None:
    """Return no anchor when ellipsis fragments only exist across multiple blocks."""

    blocks = [
        ArtifactBlock(index=0, text="Alpha block ends with abc"),
        ArtifactBlock(index=1, text="Second block starts with 123"),
    ]

    anchor = create_anchor_from_excerpt(blocks, "abc ... 123")

    assert anchor is None
