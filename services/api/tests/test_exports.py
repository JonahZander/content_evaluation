"""Export tests."""

from content_evaluation.domain.models import (
    AgentCategory,
    AnalysisArtifact,
    ArtifactAnchor,
    ArtifactBlock,
    ArtifactComment,
    ArtifactDebug,
    ArtifactDocument,
    ArtifactReply,
    ArtifactSource,
    ArtifactSummary,
    ArtifactThread,
    AuthorType,
    ReviewState,
    RunConfig,
    RuntimeMode,
    SourceType,
)
from content_evaluation.services.exporting import build_json_export, build_markdown_export


def test_exports_include_comments_and_replies() -> None:
    """Render one artifact as Markdown and JSON."""

    block = ArtifactBlock(index=0, text="This post explains how editors review content.")
    document = ArtifactDocument(
        title="Draft",
        source_type=SourceType.TEXT,
        source_label="draft",
        text=block.text,
        blocks=[block],
    )
    anchor = ArtifactAnchor(block_id=block.id, start_offset=0, end_offset=4, quote="This")
    artifact = AnalysisArtifact(
        source=ArtifactSource(source_type=SourceType.TEXT, source_label="draft"),
        document=document,
        run_config=RunConfig(selected_agents=["value"], runtime_mode=RuntimeMode.MOCK),
        anchors=[anchor],
        summary=ArtifactSummary(
            overall_score=72,
            verdict="Worth reading with edits",
            value_summary="Lead with the strongest takeaway.",
            audience_summary="Editors and content strategists.",
            novelty_score=0.42,
            ai_likelihood=0.31,
        ),
        debug=ArtifactDebug(traces=[]),
    )
    comment = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor.id,
        author_type=AuthorType.AGENT,
        author_label="value agent",
        category=AgentCategory.VALUE,
        body="Lead with the strongest takeaway.",
        review_state=ReviewState.UNCERTAIN,
    )
    comment.replies.append(
        ArtifactReply(
            comment_id=comment.id,
            author_type=AuthorType.HUMAN,
            author_label="Reviewer",
            body="Needs more examples.",
        )
    )
    artifact.threads = [ArtifactThread(anchor=anchor, comments=[comment])]

    markdown_export = build_markdown_export(artifact)
    json_export = build_json_export(artifact)

    assert "## Comments" in markdown_export
    assert "Reply (Reviewer)" in markdown_export
    assert '"threads"' in json_export
    assert '"artifact_id"' in json_export
