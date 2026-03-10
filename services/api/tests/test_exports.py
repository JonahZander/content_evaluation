"""Export tests."""

from content_evaluation.domain.models import (
    AgentCategory,
    AuthorType,
    Comment,
    CommentReply,
    CommentThread,
    DocumentBlock,
    NormalizedDocument,
    ReviewState,
    RunDetail,
    RunMetadata,
    RunSummary,
    SourceType,
    TextAnchor,
)
from content_evaluation.services.exporting import build_json_export, build_markdown_export


def test_exports_include_comments_and_replies() -> None:
    """Render one run detail as Markdown and JSON."""

    run = RunMetadata(source_type=SourceType.TEXT, source_label="draft")
    block = DocumentBlock(index=0, text="This post explains how editors review content.")
    document = NormalizedDocument(
        title="Draft",
        source_type=SourceType.TEXT,
        source_label="draft",
        text=block.text,
        blocks=[block],
    )
    anchor = TextAnchor(block_id=block.id, start_offset=0, end_offset=4, quote="This")
    comment = Comment(
        run_id=run.id,
        anchor_id=anchor.id,
        author_type=AuthorType.AGENT,
        author_label="value agent",
        category=AgentCategory.VALUE,
        body="Lead with the strongest takeaway.",
        review_state=ReviewState.UNCERTAIN,
    )
    comment.replies.append(
        CommentReply(
            comment_id=comment.id,
            author_type=AuthorType.HUMAN,
            author_label="Reviewer",
            body="Needs more examples.",
        )
    )
    detail = RunDetail(
        run=run,
        document=document,
        anchors=[anchor],
        threads=[CommentThread(anchor=anchor, comments=[comment])],
        summary=RunSummary(
            overall_score=72,
            verdict="Worth reading with edits",
            value_summary="Lead with the strongest takeaway.",
            audience_summary="Editors and content strategists.",
            novelty_score=0.42,
            ai_likelihood=0.31,
        ),
    )

    markdown_export = build_markdown_export(detail)
    json_export = build_json_export(detail)

    assert "## Comments" in markdown_export
    assert "Reply (Reviewer)" in markdown_export
    assert '"threads"' in json_export
    assert '"run_metadata"' in json_export
