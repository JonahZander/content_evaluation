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

    matches = _find_normalized_spans(block_text, excerpt)
    if not matches:
        return None
    return matches[0]


def _find_normalized_spans(block_text: str, excerpt: str) -> list[tuple[int, int]]:
    """Locate all normalized matches for one excerpt within a block."""

    normalized_block, block_map = _normalize_with_map(block_text)
    normalized_excerpt, excerpt_map = _normalize_with_map(excerpt)
    if not normalized_block or not normalized_excerpt or not excerpt_map:
        return []

    matches: list[tuple[int, int]] = []
    search_start = 0
    while search_start < len(normalized_block):
        position = normalized_block.find(normalized_excerpt, search_start)
        if position < 0:
            break
        start_offset = block_map[position]
        end_index = position + len(normalized_excerpt) - 1
        end_offset = block_map[end_index] + 1
        matches.append((start_offset, end_offset))
        search_start = position + 1
    return matches


def _find_ellipsis_span(block_text: str, excerpt: str) -> tuple[int, int] | None:
    """Locate excerpts that were truncated with ellipses."""

    if ELLIPSIS_PATTERN.search(excerpt) is None:
        return None
    segments = [segment.strip() for segment in ELLIPSIS_PATTERN.split(excerpt) if segment.strip()]
    if not segments:
        return None

    first_segment_matches = _find_normalized_spans(block_text, segments[0])
    for block_start, first_end in first_segment_matches:
        search_start = first_end
        block_end = first_end
        matched = True
        for segment in segments[1:]:
            match = _find_normalized_span(block_text[search_start:], segment)
            if match is None:
                matched = False
                break
            segment_start, segment_end = match
            block_end = search_start + segment_end
            search_start += segment_end
        if matched:
            return block_start, block_end
    return None


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
