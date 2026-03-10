"""Anchor generation helpers."""

from __future__ import annotations

from collections.abc import Iterable

from content_evaluation.domain.models import DocumentBlock, TextAnchor


def create_anchor_from_excerpt(blocks: Iterable[DocumentBlock], excerpt: str) -> TextAnchor:
    """Create one anchor by locating an excerpt in the blocks."""

    stripped_excerpt = excerpt.strip().strip('"')
    for block in blocks:
        position = block.text.find(stripped_excerpt)
        if position >= 0:
            return TextAnchor(
                block_id=block.id,
                start_offset=position,
                end_offset=position + len(stripped_excerpt),
                quote=stripped_excerpt,
            )

    fallback_block = next(iter(blocks))
    quote = stripped_excerpt or fallback_block.text[: min(len(fallback_block.text), 120)]
    return TextAnchor(
        block_id=fallback_block.id,
        start_offset=0,
        end_offset=min(len(fallback_block.text), len(quote)),
        quote=quote,
    )
