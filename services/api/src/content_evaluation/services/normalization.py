"""Document normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable

from content_evaluation.domain.models import DocumentBlock, NormalizedDocument, RunInput


def normalize_text(input_data: RunInput, extracted_text: str, title: str | None = None) -> NormalizedDocument:
    """Normalize raw text into ordered blocks."""

    cleaned_text = extracted_text.strip()
    paragraphs = [chunk.strip() for chunk in cleaned_text.split("\n\n") if chunk.strip()]
    if not paragraphs:
        paragraphs = [cleaned_text]
    blocks = [DocumentBlock(index=index, text=text) for index, text in enumerate(paragraphs)]
    resolved_title = title or input_data.title or input_data.source_label
    return NormalizedDocument(
        title=resolved_title,
        source_type=input_data.source_type,
        source_label=input_data.source_label,
        text="\n\n".join(paragraphs),
        blocks=blocks,
    )


def build_similarity_query(title: str, blocks: Iterable[DocumentBlock]) -> str:
    """Build one query string for similarity search."""

    first_block = next(iter(blocks), None)
    base = first_block.text if first_block else title
    return f"{title} {base[:180]}".strip()
