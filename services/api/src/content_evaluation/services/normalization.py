"""Document normalization helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable

from markdown_it import MarkdownIt
from markdown_it.token import Token

from content_evaluation.domain.models import (
    ArtifactBlock,
    ArtifactBlockKind,
    ArtifactCleanerAudit,
    ArtifactCleanerFlaggedBlock,
    ArtifactCleanerRemovedBlock,
    ArtifactDocument,
    ArtifactInlineMark,
    ArtifactInlineMarkKind,
    ArtifactListItem,
    CleanerRemovalReason,
    ContentFormat,
    RunInput,
)

_markdown = MarkdownIt("commonmark", {"html": False})
OVERSIZED_BLOCK_CHAR_LIMIT = 1800
OVERSIZED_BLOCK_SENTENCE_LIMIT = 12
TARGET_CHUNK_MIN = 700
TARGET_CHUNK_MAX = 1100
SENTENCE_PATTERN = re.compile(r".+?(?:[.!?](?=\s|$)|$)", re.S)
TASK_LIST_ITEM_PATTERN = re.compile(r"^\[[ xX]\](?:\s|$)")
PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore previous instructions\b", re.I),
    re.compile(r"\byou are chatgpt\b", re.I),
    re.compile(r"\bas an ai\b", re.I),
    re.compile(r"\b(system prompt|developer message|tool call)\b", re.I),
)
SITE_CHROME_PATTERNS = (
    re.compile(r"\b(home|about|contact|login|sign in|sign up)\b", re.I),
    re.compile(r"\b(privacy policy|cookie policy|cookie settings|terms of service)\b", re.I),
    re.compile(r"\b(breadcrumb|breadcrumbs|footer|navigation)\b", re.I),
    re.compile(r"\b(share|follow|subscribe|newsletter)\b", re.I),
)
ADVERTISEMENT_PATTERNS = (
    re.compile(r"\b(advertisement|advertorial|sponsored|sponsor content|paid promotion)\b", re.I),
    re.compile(r"\b(affiliate|partner link|promo code)\b", re.I),
)
EXTRACTION_JUNK_PATTERNS = (
    re.compile(r"^(?:read more|continue reading|related articles?|related posts?|more from this author)$", re.I),
    re.compile(r"^(?:share this|print this|email this)$", re.I),
    re.compile(r"^[-*_]{3,}$"),
)
SUSPICIOUS_PATTERNS = (
    re.compile(r"\b(editor'?s note|update:|updated:|disclosure:)\b", re.I),
    re.compile(r"\b(photo credit|image credit|caption)\b", re.I),
)


def normalize_text(
    input_data: RunInput,
    extracted_text: str,
    title: str | None = None,
    *,
    content_format: ContentFormat = ContentFormat.PLAIN_TEXT,
) -> ArtifactDocument:
    """Normalize raw content into ordered blocks."""

    cleaned_text = extracted_text.strip()
    if content_format is ContentFormat.MARKDOWN:
        blocks = _normalize_markdown_blocks(cleaned_text)
    else:
        blocks = _normalize_plain_text_blocks(cleaned_text)

    if not blocks:
        blocks = _normalize_plain_text_blocks(cleaned_text)
    cleaned_blocks, cleaner_audit = _clean_blocks(blocks)
    if not cleaned_blocks:
        cleaned_blocks = blocks
        cleaner_audit = ArtifactCleanerAudit(
            suspicious_blocks=[
                ArtifactCleanerFlaggedBlock(
                    original_index=block.index,
                    text=block.text,
                    reason=CleanerRemovalReason.SUSPICIOUS_NON_ARTICLE,
                )
                for block in blocks
            ]
        )
    cleaner_output = _render_cleaner_output(cleaned_blocks, content_format)
    blocks = _split_oversized_blocks(cleaned_blocks)

    resolved_title = title or input_data.title or input_data.source_label
    return ArtifactDocument(
        title=resolved_title,
        source_type=input_data.source_type,
        source_label=input_data.source_label,
        content_format=content_format,
        raw_content=cleaner_output,
        text="\n\n".join(block.text for block in blocks if block.text),
        blocks=blocks,
        cleaner_audit=cleaner_audit,
    )


def build_similarity_query(title: str, blocks: Iterable[ArtifactBlock]) -> str:
    """Build one query string from the first visible block."""

    first_block = next(iter(blocks), None)
    base = first_block.text if first_block else title
    return f"{title} {base[:180]}".strip()


def _normalize_plain_text_blocks(cleaned_text: str) -> list[ArtifactBlock]:
    """Split plain text into paragraph blocks."""

    paragraphs = [chunk.strip() for chunk in cleaned_text.split("\n\n") if chunk.strip()]
    if not paragraphs and cleaned_text:
        paragraphs = [cleaned_text]

    return [
        ArtifactBlock(
            index=index,
            text=text,
            kind=ArtifactBlockKind.PARAGRAPH,
            markdown=text,
        )
        for index, text in enumerate(paragraphs)
    ]


def _normalize_markdown_blocks(cleaned_text: str) -> list[ArtifactBlock]:
    """Parse markdown into block-level document nodes."""

    if not cleaned_text:
        return []

    lines = cleaned_text.splitlines()
    tokens = _markdown.parse(cleaned_text)
    blocks: list[ArtifactBlock] = []
    index = 0
    token_index = 0
    while token_index < len(tokens):
        token = tokens[token_index]
        if token.type == "heading_open" and token_index + 1 < len(tokens):
            inline_token = tokens[token_index + 1]
            text, marks = _extract_inline_content(inline_token)
            if text.strip():
                blocks.append(
                    ArtifactBlock(
                        index=index,
                        text=text,
                        kind=ArtifactBlockKind.HEADING,
                        markdown=_source_slice(lines, token.map) or inline_token.content,
                        level=int(token.tag[1]) if len(token.tag) == 2 and token.tag.startswith("h") else 1,
                        marks=marks,
                    )
                )
                index += 1
            token_index += 3
            continue

        if token.type in {"bullet_list_open", "ordered_list_open"}:
            list_block, next_token_index = _normalize_markdown_list_block(tokens, token_index, lines, index)
            if list_block is not None:
                blocks.append(list_block)
                index += 1
                token_index = next_token_index
                continue

        if token.type == "paragraph_open" and token_index + 1 < len(tokens):
            inline_token = tokens[token_index + 1]
            text, marks = _extract_inline_content(inline_token)
            if text.strip():
                blocks.append(
                    ArtifactBlock(
                        index=index,
                        text=text,
                        kind=ArtifactBlockKind.PARAGRAPH,
                        markdown=_source_slice(lines, token.map) or inline_token.content,
                        marks=marks,
                    )
                )
                index += 1
            token_index += 3
            continue

        if token.type == "fence":
            code_text = token.content.rstrip("\n")
            if code_text.strip():
                blocks.append(
                    ArtifactBlock(
                        index=index,
                        text=code_text,
                        kind=ArtifactBlockKind.CODE,
                        markdown=_source_slice(lines, token.map) or token.content,
                        language=token.info.strip().split()[0] if token.info.strip() else None,
                    )
                )
                index += 1
            token_index += 1
            continue

        token_index += 1

    return blocks


def _split_oversized_blocks(blocks: list[ArtifactBlock]) -> list[ArtifactBlock]:
    """Split collapsed plain-text paragraphs into smaller review blocks."""

    expanded: list[ArtifactBlock] = []
    for block in blocks:
        expanded.extend(_split_block_if_needed(block))

    return [
        ArtifactBlock(
            index=index,
            text=block.text,
            kind=block.kind,
            origin=block.origin,
            markdown=block.markdown,
            level=block.level,
            language=block.language,
            marks=list(block.marks),
            list_items=list(block.list_items),
            ordered=block.ordered,
            start_number=block.start_number,
        )
        for index, block in enumerate(expanded)
    ]


def _clean_blocks(blocks: list[ArtifactBlock]) -> tuple[list[ArtifactBlock], ArtifactCleanerAudit]:
    """Remove obvious junk while preserving uncertain article content."""

    cleaned: list[ArtifactBlock] = []
    removed_blocks: list[ArtifactCleanerRemovedBlock] = []
    suspicious_blocks: list[ArtifactCleanerFlaggedBlock] = []
    seen_normalized_texts: set[str] = set()

    for block in blocks:
        normalized_text = _normalize_block_text(block.text)
        if not normalized_text:
            removed_blocks.append(
                ArtifactCleanerRemovedBlock(
                    original_index=block.index,
                    text=block.text,
                    removal_reason=CleanerRemovalReason.EXTRACTION_JUNK,
                )
            )
            continue

        if normalized_text in seen_normalized_texts:
            removed_blocks.append(
                ArtifactCleanerRemovedBlock(
                    original_index=block.index,
                    text=block.text,
                    removal_reason=CleanerRemovalReason.DUPLICATE,
                )
            )
            continue

        removal_reason = _removal_reason_for_block(block.text)
        if removal_reason is not None:
            removed_blocks.append(
                ArtifactCleanerRemovedBlock(
                    original_index=block.index,
                    text=block.text,
                    removal_reason=removal_reason,
                )
            )
            continue

        if _is_suspicious_block(block.text):
            suspicious_blocks.append(
                ArtifactCleanerFlaggedBlock(
                    original_index=block.index,
                    text=block.text,
                    reason=CleanerRemovalReason.SUSPICIOUS_NON_ARTICLE,
                )
            )

        cleaned.append(block)
        seen_normalized_texts.add(normalized_text)

    return cleaned, ArtifactCleanerAudit(removed_blocks=removed_blocks, suspicious_blocks=suspicious_blocks)


def _render_cleaner_output(blocks: list[ArtifactBlock], content_format: ContentFormat) -> str:
    """Serialize cleaner-retained blocks into the canonical analysis content."""

    if content_format is ContentFormat.MARKDOWN:
        return "\n\n".join((block.markdown or block.text).strip() for block in blocks if block.text.strip())
    return "\n\n".join(block.text.strip() for block in blocks if block.text.strip())


def _removal_reason_for_block(text: str) -> CleanerRemovalReason | None:
    """Classify one block that should be removed before analysis."""

    if _matches_any(PROMPT_INJECTION_PATTERNS, text):
        return CleanerRemovalReason.PROMPT_INJECTION
    if _matches_any(ADVERTISEMENT_PATTERNS, text):
        return CleanerRemovalReason.ADVERTISEMENT
    if _matches_any(SITE_CHROME_PATTERNS, text):
        return CleanerRemovalReason.SITE_CHROME
    if _matches_any(EXTRACTION_JUNK_PATTERNS, text):
        return CleanerRemovalReason.EXTRACTION_JUNK
    if _looks_like_duplicate_or_fragment(text):
        return CleanerRemovalReason.EXTRACTION_JUNK
    return None


def _is_suspicious_block(text: str) -> bool:
    """Return whether one retained block should be flagged for review."""

    if _matches_any(SUSPICIOUS_PATTERNS, text):
        return True
    return len(text.strip()) < 80 and bool(re.search(r"\b(note|update|disclosure|credit)\b", text, re.I))


def _looks_like_duplicate_or_fragment(text: str) -> bool:
    """Detect orphaned labels and broken extraction fragments conservatively."""

    stripped = text.strip()
    if len(stripped) <= 3:
        return True
    if stripped.endswith(":") and len(stripped) < 40 and len(stripped.split()) <= 4:
        return True
    if stripped.casefold() in {"share", "follow", "comments", "read more", "related", "next", "previous"}:
        return True
    return False


def _normalize_block_text(text: str) -> str:
    """Build a conservative duplicate-matching key for one block."""

    return re.sub(r"\s+", " ", text).strip().casefold()


def _matches_any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    """Return whether any pattern matches the block text."""

    return any(pattern.search(text) for pattern in patterns)


def _split_block_if_needed(block: ArtifactBlock) -> list[ArtifactBlock]:
    """Split one oversized plain paragraph into conservative sentence chunks."""

    if not _should_split_block(block):
        return [block]

    sentences = [match.group(0).strip() for match in SENTENCE_PATTERN.finditer(block.text) if match.group(0).strip()]
    if len(sentences) <= 1:
        return [block]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for sentence in sentences:
        addition = len(sentence) if not current else len(sentence) + 1
        if current and current_length + addition > TARGET_CHUNK_MAX and current_length >= TARGET_CHUNK_MIN:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_length = len(sentence)
            continue
        current.append(sentence)
        current_length += addition

    if current:
        chunks.append(" ".join(current).strip())

    if len(chunks) <= 1:
        return [block]

    return [
        ArtifactBlock(
            index=block.index,
            text=chunk,
            kind=block.kind,
            origin=block.origin,
            markdown=chunk,
            level=block.level,
            language=block.language,
            marks=[],
            ordered=block.ordered,
            start_number=block.start_number,
        )
        for chunk in chunks
    ]


def _should_split_block(block: ArtifactBlock) -> bool:
    """Return whether one block is oversized plain prose."""

    if block.kind != ArtifactBlockKind.PARAGRAPH:
        return False
    if block.origin.value != "source":
        return False
    if block.marks:
        return False
    if block.markdown is not None and block.markdown != block.text:
        return False
    sentence_count = len([match for match in SENTENCE_PATTERN.finditer(block.text) if match.group(0).strip()])
    return len(block.text) > OVERSIZED_BLOCK_CHAR_LIMIT or sentence_count > OVERSIZED_BLOCK_SENTENCE_LIMIT


def _source_slice(lines: list[str], mapping: list[int] | None) -> str:
    """Return the source markdown lines for one block token."""

    if mapping is None or len(mapping) != 2:
        return ""
    start, end = mapping
    return "\n".join(lines[start:end]).strip()


def _normalize_markdown_list_block(
    tokens: list[Token],
    start_index: int,
    lines: list[str],
    block_index: int,
) -> tuple[ArtifactBlock | None, int]:
    """Collapse one simple top-level markdown list into a single block."""

    list_token = tokens[start_index]
    if list_token.type not in {"bullet_list_open", "ordered_list_open"}:
        return None, start_index + 1
    if list_token.level != 0:
        return None, start_index + 1

    closing_type = "bullet_list_close" if list_token.type == "bullet_list_open" else "ordered_list_close"
    token_index = start_index + 1
    item_texts: list[str] = []
    item_marks: list[list[ArtifactInlineMark]] = []
    while token_index < len(tokens):
        token = tokens[token_index]
        if token.type == closing_type:
            break

        if token.type != "list_item_open":
            return None, start_index + 1

        if token_index + 4 >= len(tokens):
            return None, start_index + 1

        paragraph_open = tokens[token_index + 1]
        inline_token = tokens[token_index + 2]
        paragraph_close = tokens[token_index + 3]
        list_item_close = tokens[token_index + 4]

        if (
            paragraph_open.type != "paragraph_open"
            or inline_token.type != "inline"
            or paragraph_close.type != "paragraph_close"
            or list_item_close.type != "list_item_close"
        ):
            return None, start_index + 1

        if TASK_LIST_ITEM_PATTERN.match(inline_token.content.strip()):
            return None, start_index + 1

        text, marks = _extract_inline_content(inline_token)
        if not text.strip():
            return None, start_index + 1

        item_texts.append(text)
        item_marks.append(marks)
        token_index += 5

    if token_index >= len(tokens) or tokens[token_index].type != closing_type or not item_texts:
        return None, start_index + 1

    block_text, list_items, marks = _build_list_text_and_metadata(item_texts, item_marks)
    start_number = None
    if list_token.type == "ordered_list_open":
        raw_start = list_token.attrGet("start")
        parsed_start = int(raw_start) if raw_start is not None else 1
        if parsed_start != 1:
            start_number = parsed_start

    return (
        ArtifactBlock(
            index=block_index,
            text=block_text,
            kind=ArtifactBlockKind.LIST,
            markdown=_source_slice(lines, list_token.map) or block_text,
            marks=marks,
            list_items=list_items,
            ordered=list_token.type == "ordered_list_open",
            start_number=start_number,
        ),
        token_index + 1,
    )


def _build_list_text_and_metadata(
    item_texts: list[str],
    item_marks: list[list[ArtifactInlineMark]],
) -> tuple[str, list[ArtifactListItem], list[ArtifactInlineMark]]:
    """Build joined list text plus rebased items and marks."""

    joined_parts: list[str] = []
    list_items: list[ArtifactListItem] = []
    rebased_marks: list[ArtifactInlineMark] = []
    offset = 0

    for item_index, item_text in enumerate(item_texts):
        if item_index > 0:
            joined_parts.append("\n")
            offset += 1

        item_start = offset
        joined_parts.append(item_text)
        offset += len(item_text)
        list_items.append(
            ArtifactListItem(
                text=item_text,
                start_offset=item_start,
                end_offset=offset,
            )
        )
        rebased_marks.extend(
            ArtifactInlineMark(
                start_offset=item_start + mark.start_offset,
                end_offset=item_start + mark.end_offset,
                kind=mark.kind,
                href=mark.href,
            )
            for mark in item_marks[item_index]
        )

    return (
        "".join(joined_parts),
        list_items,
        sorted(rebased_marks, key=lambda mark: (mark.start_offset, mark.end_offset, mark.kind.value)),
    )


def _extract_inline_content(token: Token) -> tuple[str, list[ArtifactInlineMark]]:
    """Return visible plain text plus inline formatting spans."""

    if not token.children:
        return token.content, []

    parts: list[str] = []
    marks: list[ArtifactInlineMark] = []
    open_marks: dict[ArtifactInlineMarkKind, list[int]] = {
        ArtifactInlineMarkKind.STRONG: [],
        ArtifactInlineMarkKind.EMPHASIS: [],
    }
    open_links: list[tuple[int, str | None]] = []
    offset = 0

    for child in token.children:
        if child.type == "text":
            parts.append(child.content)
            offset += len(child.content)
            continue
        if child.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
            offset += 1
            continue
        if child.type == "code_inline":
            parts.append(child.content)
            marks.append(
                ArtifactInlineMark(
                    start_offset=offset,
                    end_offset=offset + len(child.content),
                    kind=ArtifactInlineMarkKind.CODE,
                )
            )
            offset += len(child.content)
            continue
        if child.type == "image":
            parts.append(child.content)
            offset += len(child.content)
            continue
        if child.type == "strong_open":
            open_marks[ArtifactInlineMarkKind.STRONG].append(offset)
            continue
        if child.type == "strong_close" and open_marks[ArtifactInlineMarkKind.STRONG]:
            start = open_marks[ArtifactInlineMarkKind.STRONG].pop()
            if start < offset:
                marks.append(
                    ArtifactInlineMark(
                        start_offset=start,
                        end_offset=offset,
                        kind=ArtifactInlineMarkKind.STRONG,
                    )
                )
            continue
        if child.type == "em_open":
            open_marks[ArtifactInlineMarkKind.EMPHASIS].append(offset)
            continue
        if child.type == "em_close" and open_marks[ArtifactInlineMarkKind.EMPHASIS]:
            start = open_marks[ArtifactInlineMarkKind.EMPHASIS].pop()
            if start < offset:
                marks.append(
                    ArtifactInlineMark(
                        start_offset=start,
                        end_offset=offset,
                        kind=ArtifactInlineMarkKind.EMPHASIS,
                    )
                )
            continue
        if child.type == "link_open":
            href = child.attrGet("href")
            open_links.append((offset, href if isinstance(href, str) else None))
            continue
        if child.type == "link_close" and open_links:
            start, href = open_links.pop()
            if start < offset and href:
                marks.append(
                    ArtifactInlineMark(
                        start_offset=start,
                        end_offset=offset,
                        kind=ArtifactInlineMarkKind.LINK,
                        href=href,
                    )
                )
            continue

    return "".join(parts), sorted(marks, key=lambda mark: (mark.start_offset, mark.end_offset, mark.kind.value))
