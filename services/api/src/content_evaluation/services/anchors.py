"""Anchor generation helpers."""

from __future__ import annotations

from collections.abc import Iterable
import re

from content_evaluation.domain.models import ArtifactAnchor, ArtifactBlock


ELLIPSIS_PATTERN = re.compile(r"(?:\.\.\.|…)+")


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace while keeping a map to original offsets."""

    normalized_parts: list[str] = []
    position_map: list[int] = []
    previous_was_space = False

    for index, character in enumerate(text):
        normalized_character = " " if character.isspace() else character
        if normalized_character == " ":
            if previous_was_space:
                continue
            previous_was_space = True
        else:
            previous_was_space = False

        normalized_parts.append(normalized_character)
        position_map.append(index)

    normalized = "".join(normalized_parts).strip()
    if not normalized:
        return "", []

    start = "".join(normalized_parts).find(normalized)
    end = start + len(normalized)
    return normalized, position_map[start:end]


def _find_normalized_span(block_text: str, excerpt: str) -> tuple[int, int] | None:
    """Locate one excerpt after normalizing whitespace."""

    normalized_block, block_map = _normalize_with_map(block_text)
    normalized_excerpt, excerpt_map = _normalize_with_map(excerpt)
    if not normalized_block or not normalized_excerpt or not excerpt_map:
        return None

    position = normalized_block.find(normalized_excerpt)
    if position < 0:
        return None

    start_offset = block_map[position]
    end_index = position + len(normalized_excerpt) - 1
    end_offset = block_map[end_index] + 1
    return start_offset, end_offset


def _find_ellipsis_span(block_text: str, excerpt: str) -> tuple[int, int] | None:
    """Locate excerpts that were truncated with ellipses."""

    segments = [segment.strip() for segment in ELLIPSIS_PATTERN.split(excerpt) if segment.strip()]
    if len(segments) < 2:
        return None

    search_start = 0
    block_start: int | None = None
    block_end: int | None = None
    for segment in segments:
        match = _find_normalized_span(block_text[search_start:], segment)
        if match is None:
            return None
        segment_start, segment_end = match
        absolute_start = search_start + segment_start
        absolute_end = search_start + segment_end
        if block_start is None:
            block_start = absolute_start
        block_end = absolute_end
        search_start = absolute_end

    if block_start is None or block_end is None:
        return None
    return block_start, block_end


def create_anchor_from_excerpt(blocks: Iterable[ArtifactBlock], excerpt: str) -> ArtifactAnchor | None:
    """Create one anchor by locating an excerpt in the blocks."""

    stripped_excerpt = excerpt.strip().strip('"')
    for block in blocks:
        position = _find_normalized_span(block.text, stripped_excerpt)
        if position is not None:
            start_offset, end_offset = position
            return ArtifactAnchor(
                block_id=block.id,
                start_offset=start_offset,
                end_offset=end_offset,
                quote=stripped_excerpt,
            )

        ellipsis_position = _find_ellipsis_span(block.text, stripped_excerpt)
        if ellipsis_position is not None:
            start_offset, end_offset = ellipsis_position
            return ArtifactAnchor(
                block_id=block.id,
                start_offset=start_offset,
                end_offset=end_offset,
                quote=stripped_excerpt,
            )

    return None
