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
ATTRIBUTION_PATTERN = re.compile(
    r"""^.*?\b(?:states?\s+that|said\s+that|notes?\s+that|reports?\s+that|"""
    r"""found\s+that|shows?\s+that|indicates?\s+that|suggests?\s+that|"""
    r"""according\s+to\s+\w[\w\s,']*?(?:,|:))\s*[:"]?\s*""",
    re.IGNORECASE,
)
UNMATCHED_SECTION_MARKERS = ("## Unmatched references", "Unmatched references")
WINDOW_SEPARATOR = "\n\n"
MAX_BLOCK_WINDOW = 3
MAX_FUZZY_EDIT_DISTANCE = 2
MIN_SUBSTRING_RATIO = 0.45


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


def _strip_attribution(excerpt: str) -> str | None:
    """Strip leading attribution framing and return the core quote, if any."""

    stripped = ATTRIBUTION_PATTERN.sub("", excerpt).strip().strip('"').strip()
    if stripped and len(stripped) >= 20 and stripped != excerpt:
        return stripped
    return None


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


def _normalized_search_payload(text: str, excerpt: str) -> tuple[str, list[int], str] | None:
    """Return normalized text state used by exact and fuzzy matching."""

    normalized_text, text_map = _normalize_with_map(text)
    normalized_excerpt, excerpt_map = _normalize_with_map(excerpt)
    if not normalized_text or not normalized_excerpt or not excerpt_map:
        return None
    return normalized_text, text_map, normalized_excerpt


def _find_normalized_spans(text: str, excerpt: str) -> list[tuple[int, int]]:
    """Locate all normalized matches for one excerpt within a source string."""

    payload = _normalized_search_payload(text, excerpt)
    if payload is None:
        return []
    normalized_text, text_map, normalized_excerpt = payload

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


def _levenshtein_distance_with_cap(left: str, right: str, max_distance: int) -> int | None:
    """Return edit distance when it is within the requested cap."""

    if abs(len(left) - len(right)) > max_distance:
        return None

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current[right_index - 1] + 1
            delete_cost = previous[right_index] + 1
            replace_cost = previous[right_index - 1] + (0 if left_char == right_char else 1)
            value = min(insert_cost, delete_cost, replace_cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > max_distance:
            return None
        previous = current

    distance = previous[-1]
    if distance > max_distance:
        return None
    return distance


def _find_fuzzy_normalized_span(
    text: str,
    excerpt: str,
    *,
    max_distance: int = MAX_FUZZY_EDIT_DISTANCE,
) -> tuple[int, int] | None:
    """Locate a near-match excerpt within one block using bounded edit distance."""

    payload = _normalized_search_payload(text, excerpt)
    if payload is None:
        return None
    normalized_text, text_map, normalized_excerpt = payload
    if len(normalized_excerpt) > len(normalized_text) + max_distance:
        return None

    best: tuple[int, int, int] | None = None
    min_length = max(1, len(normalized_excerpt) - max_distance)
    max_length = min(len(normalized_text), len(normalized_excerpt) + max_distance)

    for start in range(0, len(normalized_text)):
        remaining = len(normalized_text) - start
        if remaining < min_length:
            break
        candidate_max_length = min(max_length, remaining)
        for length in range(min_length, candidate_max_length + 1):
            candidate = normalized_text[start : start + length]
            distance = _levenshtein_distance_with_cap(candidate, normalized_excerpt, max_distance)
            if distance is None:
                continue
            if best is None or distance < best[0]:
                best = (distance, start, start + length)
                if distance == 1:
                    break
        if best is not None and best[0] == 0:
            break

    if best is None:
        return None

    _, start, end = best
    return text_map[start], text_map[end - 1] + 1


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


def _longest_common_substring_span(
    text: str,
    excerpt: str,
    *,
    min_ratio: float = MIN_SUBSTRING_RATIO,
) -> tuple[int, int] | None:
    """Find the best overlap between text and excerpt using longest common substring."""

    payload = _normalized_search_payload(text, excerpt)
    if payload is None:
        return None
    normalized_text, text_map, normalized_excerpt = payload

    if len(normalized_excerpt) < 20:
        return None

    n = len(normalized_text)
    m = len(normalized_excerpt)
    best_length = 0
    best_end_i = 0

    # Use a rolling row DP for memory efficiency
    previous = [0] * (m + 1)
    for i in range(1, n + 1):
        current = [0] * (m + 1)
        for j in range(1, m + 1):
            if normalized_text[i - 1] == normalized_excerpt[j - 1]:
                current[j] = previous[j - 1] + 1
                if current[j] > best_length:
                    best_length = current[j]
                    best_end_i = i
        previous = current

    ratio = best_length / m if m > 0 else 0
    if ratio < min_ratio:
        return None

    start_i = best_end_i - best_length
    return text_map[start_i], text_map[best_end_i - 1] + 1


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


def _find_anchor_in_single_block(block: ArtifactBlock, excerpt: str) -> ArtifactAnchor | None:
    """Return an anchor when one excerpt matches a specific block."""

    position = _find_normalized_span(block.text, excerpt)
    if position is None:
        position = _find_ellipsis_span(block.text, excerpt)
    if position is None:
        position = _find_fuzzy_normalized_span(block.text, excerpt)
    if position is None:
        return None

    start_offset, end_offset = position
    return ArtifactAnchor(
        quote=excerpt,
        match_kind=ArtifactAnchorMatchKind.SOURCE,
        segments=[
            ArtifactAnchorSegment(
                block_id=block.id,
                start_offset=start_offset,
                end_offset=end_offset,
            )
        ],
    )


def create_anchor_from_excerpt(
    blocks: Iterable[ArtifactBlock],
    excerpt: str,
    *,
    block_id: str | None = None,
) -> ArtifactAnchor | None:
    """Create one anchor by locating an excerpt in source blocks."""

    cleaned_excerpt = sanitize_excerpt(excerpt)
    if not cleaned_excerpt:
        return None

    source_blocks = _source_blocks(blocks)
    if not source_blocks:
        return None

    if block_id is not None:
        preferred_block = next((block for block in source_blocks if block.id == block_id), None)
        if preferred_block is not None:
            anchor = _find_anchor_in_single_block(preferred_block, cleaned_excerpt)
            if anchor is not None:
                return anchor

    for block in source_blocks:
        if block.id == block_id:
            continue
        anchor = _find_anchor_in_single_block(block, cleaned_excerpt)
        if anchor is not None:
            return anchor

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

    # Fallback: try again after stripping attribution framing.
    stripped = _strip_attribution(cleaned_excerpt)
    if stripped is not None:
        anchor = create_anchor_from_excerpt(blocks, stripped, block_id=block_id)
        if anchor is not None:
            # Keep the original (unstripped) quote for display.
            return ArtifactAnchor(
                quote=cleaned_excerpt,
                match_kind=anchor.match_kind,
                segments=anchor.segments,
            )

    # Last resort: longest common substring match against each source block.
    best_anchor: ArtifactAnchor | None = None
    best_ratio: float = 0.0
    for block in source_blocks:
        span = _longest_common_substring_span(block.text, cleaned_excerpt)
        if span is None:
            continue
        start_offset, end_offset = span
        match_length = end_offset - start_offset
        ratio = match_length / max(len(cleaned_excerpt), 1)
        if ratio > best_ratio:
            best_ratio = ratio
            best_anchor = ArtifactAnchor(
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

    return best_anchor
