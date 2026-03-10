"""Normalization tests."""

from content_evaluation.domain.models import RunInput, SourceType
from content_evaluation.services.normalization import build_similarity_query, normalize_text


def test_normalize_text_builds_blocks() -> None:
    """Normalize raw text into ordered blocks."""

    run_input = RunInput(source_type=SourceType.TEXT, source_label="draft", text="Alpha\n\nBeta")
    document = normalize_text(run_input, run_input.text or "")
    assert document.title == "draft"
    assert [block.text for block in document.blocks] == ["Alpha", "Beta"]


def test_similarity_query_uses_title_and_first_block() -> None:
    """Build one similarity query from the first block."""

    run_input = RunInput(source_type=SourceType.TEXT, source_label="draft", text="Alpha\n\nBeta")
    document = normalize_text(run_input, run_input.text or "")
    query = build_similarity_query(document.title, document.blocks)
    assert "draft" in query
    assert "Alpha" in query
