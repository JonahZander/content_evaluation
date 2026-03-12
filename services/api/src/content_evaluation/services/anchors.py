"""Anchor generation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re

from content_evaluation.domain.models import (
    ArtifactAnchor,
    ArtifactAnchorMatchKind,
    ArtifactAnchorSegment,
    ArtifactBlock,
    ArtifactBlockOrigin,
)


ELLIPSIS_PATTERN = re.compile(r"(?:\.\.\.|…)+")
UNMATCHED_SECTION_MARKERS = ("## Unmatched references", "Unmatched references")
WINDOW_SEPARATOR = "\n\n"
MAX_BLOCK_WINDOW = 3


@dataclass(frozen=True, slots=True)
class _WindowSegment:
    """Describe one block's span inside a concatenated search window."""

    block: ArtifactBlock
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class _BlockWindow:
    """Represent one contiguous source-block search window."""

    blocks: tuple[ArtifactBlock, ...]
    text: str
    spans: tuple[_WindowSegment, ...]


def sanitize_excerpt(excerpt: str) -> str:
    """Trim quotes and synthetic unmatched markers before anchor matching."""

    cleaned = excerpt.strip().strip('"').strip()
    if not cleaned:
        return ""

    for marker in UNMATCHED_SECTION_MARKERS:
        if marker not in cleaned:
            continue
        parts = [part.strip() for part in cleaned.split(marker) if part.strip()]
        if parts:
            cleaned = max(parts, key=len)
        else:
            cleaned = ""
        break

    return cleaned.strip()


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


def _find_normalized_span(text: str, excerpt: str) -> tuple[int, int] | None:
    """Locate one excerpt after normalizing whitespace."""

    matches = _find_normalized_spans(text, excerpt)
    if not matches:
        return None
    return matches[0]


def _find_normalized_spans(text: str, excerpt: str) -> list[tuple[int, int]]:
    """Locate all normalized matches for one excerpt within a source string."""

    normalized_text, text_map = _normalize_with_map(text)
    normalized_excerpt, excerpt_map = _normalize_with_map(excerpt)
    if not normalized_text or not normalized_excerpt or not excerpt_map:
        return []

    matches: list[tuple[int, int]] = []
    search_start = 0
    while search_start < len(normalized_text):
        position = normalized_text.find(normalized_excerpt, search_start)
        if position < 0:
            break
        start_offset = text_map[position]
        end_index = position + len(normalized_excerpt) - 1
        end_offset = text_map[end_index] + 1
        matches.append((start_offset, end_offset))
        search_start = position + 1
    return matches


def _find_ellipsis_span(text: str, excerpt: str) -> tuple[int, int] | None:
    """Locate excerpts that were truncated with ellipses."""

    if ELLIPSIS_PATTERN.search(excerpt) is None:
        return None
    segments = [segment.strip() for segment in ELLIPSIS_PATTERN.split(excerpt) if segment.strip()]
    if not segments:
        return None

    first_segment_matches = _find_normalized_spans(text, segments[0])
    for text_start, first_end in first_segment_matches:
        search_start = first_end
        text_end = first_end
        matched = True
        for segment in segments[1:]:
            match = _find_normalized_span(text[search_start:], segment)
            if match is None:
                matched = False
                break
            _, segment_end = match
            text_end = search_start + segment_end
            search_start += segment_end
        if matched:
            return text_start, text_end
    return None


def _source_blocks(blocks: Iterable[ArtifactBlock]) -> list[ArtifactBlock]:
    """Return only original source blocks for anchor matching."""

    return [
        block
        for block in blocks
        if block.origin == ArtifactBlockOrigin.SOURCE and block.text.strip()
    ]


def _build_window(blocks: list[ArtifactBlock]) -> _BlockWindow:
    """Build one virtual text window from adjacent blocks."""

    parts: list[str] = []
    spans: list[_WindowSegment] = []
    cursor = 0

    for index, block in enumerate(blocks):
        if index > 0:
            parts.append(WINDOW_SEPARATOR)
            cursor += len(WINDOW_SEPARATOR)
        start_offset = cursor
        parts.append(block.text)
        cursor += len(block.text)
        spans.append(_WindowSegment(block=block, start_offset=start_offset, end_offset=cursor))

    return _BlockWindow(blocks=tuple(blocks), text="".join(parts), spans=tuple(spans))


def _build_windows(blocks: list[ArtifactBlock], window_size: int) -> list[_BlockWindow]:
    """Build every contiguous window for the requested size."""

    return [
        _build_window(blocks[index : index + window_size])
        for index in range(0, len(blocks) - window_size + 1)
    ]


def _segments_for_match(window: _BlockWindow, start_offset: int, end_offset: int) -> list[ArtifactAnchorSegment]:
    """Map one virtual window span back into block-local anchor segments."""

    segments: list[ArtifactAnchorSegment] = []
    for span in window.spans:
        overlap_start = max(start_offset, span.start_offset)
        overlap_end = min(end_offset, span.end_offset)
        if overlap_start >= overlap_end:
            continue
        segments.append(
            ArtifactAnchorSegment(
                block_id=span.block.id,
                start_offset=overlap_start - span.start_offset,
                end_offset=overlap_end - span.start_offset,
            )
        )
    return segments


def _anchor_from_segments(segments: list[ArtifactAnchorSegment], quote: str) -> ArtifactAnchor | None:
    """Build one source anchor from ordered segments."""

    if not segments:
        return None
    return ArtifactAnchor(
        quote=quote,
        match_kind=ArtifactAnchorMatchKind.SOURCE,
        segments=segments,
    )


def create_anchor_from_excerpt(blocks: Iterable[ArtifactBlock], excerpt: str) -> ArtifactAnchor | None:
    """Create one anchor by locating an excerpt in source blocks."""

    cleaned_excerpt = sanitize_excerpt(excerpt)
    if not cleaned_excerpt:
        return None

    source_blocks = _source_blocks(blocks)
    if not source_blocks:
        return None

    for block in source_blocks:
        position = _find_normalized_span(block.text, cleaned_excerpt)
        if position is not None:
            start_offset, end_offset = position
            return ArtifactAnchor(
                quote=cleaned_excerpt,
                match_kind=ArtifactAnchorMatchKind.SOURCE,
                segments=[
                    ArtifactAnchorSegment(
                        block_id=block.id,
                        start_offset=start_offset,
                        end_offset=end_offset,
                    )
                ],
            )

        ellipsis_position = _find_ellipsis_span(block.text, cleaned_excerpt)
        if ellipsis_position is not None:
            start_offset, end_offset = ellipsis_position
            return ArtifactAnchor(
                quote=cleaned_excerpt,
                match_kind=ArtifactAnchorMatchKind.SOURCE,
                segments=[
                    ArtifactAnchorSegment(
                        block_id=block.id,
                        start_offset=start_offset,
                        end_offset=end_offset,
                    )
                ],
            )

    for window_size in range(2, min(MAX_BLOCK_WINDOW, len(source_blocks)) + 1):
        for window in _build_windows(source_blocks, window_size):
            position = _find_normalized_span(window.text, cleaned_excerpt)
            if position is not None:
                start_offset, end_offset = position
                anchor = _anchor_from_segments(_segments_for_match(window, start_offset, end_offset), cleaned_excerpt)
                if anchor is not None:
                    return anchor

            ellipsis_position = _find_ellipsis_span(window.text, cleaned_excerpt)
            if ellipsis_position is not None:
                start_offset, end_offset = ellipsis_position
                anchor = _anchor_from_segments(_segments_for_match(window, start_offset, end_offset), cleaned_excerpt)
                if anchor is not None:
                    return anchor

    return None
