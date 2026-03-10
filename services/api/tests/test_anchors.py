"""Anchor generation tests."""

from content_evaluation.domain.models import ArtifactBlock
from content_evaluation.services.anchors import create_anchor_from_excerpt


def test_create_anchor_from_excerpt_finds_offsets() -> None:
    """Locate an excerpt within a block."""

    block = ArtifactBlock(index=0, text="Editors should trim repeated paragraphs.")
    anchor = create_anchor_from_excerpt([block], "trim repeated")
    assert anchor.block_id == block.id
    assert anchor.start_offset == 15
    assert anchor.quote == "trim repeated"
