"""Normalization tests."""

from content_evaluation.domain.models import ContentFormat, RunInput, SourceType
from content_evaluation.services.normalization import build_similarity_query, normalize_text


def test_normalize_text_builds_blocks() -> None:
    """Normalize raw text into ordered blocks."""

    run_input = RunInput(source_type=SourceType.TEXT, source_label="draft", text="Alpha\n\nBeta")
    document = normalize_text(run_input, run_input.text or "")
    assert document.title == "draft"
    assert [block.text for block in document.blocks] == ["Alpha", "Beta"]
    assert document.content_format == ContentFormat.PLAIN_TEXT


def test_normalize_markdown_builds_heading_marks_and_code_blocks() -> None:
    """Normalize markdown into structured render blocks."""

    run_input = RunInput(
      source_type=SourceType.TEXT,
      source_label="draft",
      text="## Title\n\nThis paragraph uses **bold** and *italic* text.\n\n```ts\nconst ok = true;\n```",
    )

    document = normalize_text(
        run_input,
        run_input.text or "",
        content_format=ContentFormat.MARKDOWN,
    )

    assert document.content_format == ContentFormat.MARKDOWN
    assert [block.kind.value for block in document.blocks] == ["heading", "paragraph", "code"]
    assert document.blocks[0].text == "Title"
    assert document.blocks[1].text == "This paragraph uses bold and italic text."
    assert [mark.kind.value for mark in document.blocks[1].marks] == ["strong", "emphasis"]
    assert document.blocks[2].language == "ts"
    assert document.blocks[2].text == "const ok = true;"


def test_normalize_text_splits_oversized_plain_paragraphs() -> None:
    """Split oversized plain-text imports into conservative paragraph chunks."""

    sentence = "This sentence explains a specific editorial review step."
    text = " ".join(sentence for _ in range(24))
    run_input = RunInput(source_type=SourceType.TEXT, source_label="draft", text=text)

    document = normalize_text(run_input, run_input.text or "")

    assert len(document.blocks) > 1
    assert all(block.kind.value == "paragraph" for block in document.blocks)
    assert all(block.origin.value == "source" for block in document.blocks)
    assert all(block.text for block in document.blocks)


def test_normalize_markdown_keeps_rich_paragraphs_intact_even_when_large() -> None:
    """Leave richly formatted markdown paragraphs intact instead of splitting marks."""

    sentence = "This paragraph uses **bold emphasis** to make a point."
    text = " ".join(sentence for _ in range(24))
    run_input = RunInput(source_type=SourceType.TEXT, source_label="draft", text=text)

    document = normalize_text(
        run_input,
        run_input.text or "",
        content_format=ContentFormat.MARKDOWN,
    )

    assert len(document.blocks) == 1
    assert document.blocks[0].marks


def test_similarity_query_uses_title_and_first_block() -> None:
    """Build one similarity query from the first block."""

    run_input = RunInput(source_type=SourceType.TEXT, source_label="draft", text="Alpha\n\nBeta")
    document = normalize_text(run_input, run_input.text or "")
    query = build_similarity_query(document.title, document.blocks)
    assert "draft" in query
    assert "Alpha" in query
