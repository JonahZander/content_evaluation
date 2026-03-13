"""Document normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

from content_evaluation.domain.models import (
    ArtifactBlock,
    ArtifactBlockKind,
    ArtifactDocument,
    ArtifactInlineMark,
    ArtifactInlineMarkKind,
    ContentFormat,
    RunInput,
)

_markdown = MarkdownIt("commonmark", {"html": False})
OVERSIZED_BLOCK_CHAR_LIMIT = 1800
OVERSIZED_BLOCK_SENTENCE_LIMIT = 12
TARGET_CHUNK_MIN = 700
TARGET_CHUNK_MAX = 1100
SENTENCE_PATTERN = re.compile(r".+?(?:[.!?](?=\s|$)|$)", re.S)


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
    blocks = _split_oversized_blocks(blocks)

    resolved_title = title or input_data.title or input_data.source_label
    return ArtifactDocument(
        title=resolved_title,
        source_type=input_data.source_type,
        source_label=input_data.source_label,
        content_format=content_format,
        raw_content=cleaned_text,
        text="\n\n".join(block.text for block in blocks if block.text),
        blocks=blocks,
    )


def build_fact_check_brief(title: str | None, blocks: list[ArtifactBlock]) -> str:
    """Build a research brief for the fact-check agent from a normalized document."""

    body = "\n\n".join(b.text for b in blocks[:10] if b.text)
    parts: list[str] = []
    if title:
        parts.append(f'Article title: "{title}"')
    parts.append("---")
    parts.append(body)
    return "\n".join(parts)


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
        )
        for index, block in enumerate(expanded)
    ]


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

    return "".join(parts), sorted(marks, key=lambda mark: (mark.start_offset, mark.end_offset, mark.kind.value))
