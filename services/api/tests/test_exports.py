"""Export tests."""

from content_evaluation.domain.models import (
    AgentCategory,
    AnalysisArtifact,
    ArtifactAnchor,
    ArtifactAnchorMatchKind,
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
from content_evaluation.services.exporting import (
    build_json_export,
    build_markdown_export,
    build_revised_markdown_payload,
    build_revision_suggestion_items,
    build_todo_export,
)


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


def test_todo_export_includes_only_accepted_agent_suggestions_in_article_order() -> None:
    """Render accepted suggestions as a compact todo export."""

    blocks = [
        ArtifactBlock(index=0, text="Alpha section."),
        ArtifactBlock(index=1, text="Beta section."),
        ArtifactBlock(index=2, text="Unmatched references", origin="synthetic_unmatched", kind="heading"),
    ]
    document = ArtifactDocument(
        title="Draft",
        source_type=SourceType.TEXT,
        source_label="draft",
        text="\n\n".join(block.text for block in blocks),
        blocks=blocks,
    )
    anchor_beta = ArtifactAnchor(block_id=blocks[1].id, start_offset=0, end_offset=4, quote="Beta")
    anchor_alpha = ArtifactAnchor(block_id=blocks[0].id, start_offset=0, end_offset=5, quote="Alpha")
    anchor_unmatched = ArtifactAnchor(
        block_id=blocks[2].id,
        start_offset=0,
        end_offset=20,
        quote="Fallback quote",
        match_kind=ArtifactAnchorMatchKind.SYNTHETIC_UNMATCHED,
    )
    artifact = AnalysisArtifact(
        source=ArtifactSource(source_type=SourceType.TEXT, source_label="draft"),
        document=document,
        run_config=RunConfig(selected_agents=["editorial"], runtime_mode=RuntimeMode.MOCK),
        anchors=[anchor_beta, anchor_alpha, anchor_unmatched],
    )

    accepted_alpha = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_alpha.id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Tighten the alpha section.",
        suggestion="Trim the opening claim.",
        review_state=ReviewState.ACCEPTED,
    )
    accepted_beta = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_beta.id,
        author_type=AuthorType.AGENT,
        author_label="value agent",
        category=AgentCategory.VALUE,
        body="Sharpen the beta takeaway.",
        suggestion="Move the main takeaway earlier.",
        review_state=ReviewState.ACCEPTED,
    )
    rejected = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_beta.id,
        author_type=AuthorType.AGENT,
        author_label="audience agent",
        category=AgentCategory.AUDIENCE,
        body="Not accepted.",
        suggestion="Ignore me.",
        review_state=ReviewState.REJECTED,
    )
    human_comment = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_alpha.id,
        author_type=AuthorType.HUMAN,
        author_label="Reviewer",
        category=AgentCategory.HUMAN,
        body="Reviewer note.",
        suggestion="Should not export.",
        review_state=ReviewState.ACCEPTED,
    )
    unmatched = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_unmatched.id,
        author_type=AuthorType.AGENT,
        author_label="synthesis agent",
        category=AgentCategory.SYNTHESIS,
        body="This stayed unmatched.",
        suggestion="Verify the unmatched source quote manually.",
        review_state=ReviewState.ACCEPTED,
    )

    artifact.threads = [
        ArtifactThread(anchor=anchor_beta, comments=[accepted_beta, rejected]),
        ArtifactThread(anchor=anchor_alpha, comments=[accepted_alpha, human_comment]),
        ArtifactThread(anchor=anchor_unmatched, comments=[unmatched]),
    ]

    todo_export = build_todo_export(artifact)

    assert "## Revision Todo" in todo_export
    assert '### 1. "Alpha"' in todo_export
    assert '### 2. "Beta"' in todo_export
    assert '### 3. "Fallback quote"' in todo_export
    assert "Trim the opening claim." in todo_export
    assert "Move the main takeaway earlier." in todo_export
    assert "Verify the unmatched source quote manually." in todo_export
    assert "Comment: Tighten the alpha section." in todo_export
    assert "Comment: Sharpen the beta takeaway." in todo_export
    assert "Note: Tighten the alpha section." in todo_export
    assert "Ignore me." not in todo_export
    assert "Should not export." not in todo_export
    assert "Anchor: unmatched synthetic fallback" in todo_export


def test_revised_markdown_payload_uses_accepted_suggestion_order() -> None:
    """Build a stable payload for revised markdown generation."""

    blocks = [
        ArtifactBlock(index=0, text="Alpha section."),
        ArtifactBlock(index=1, text="Beta section."),
        ArtifactBlock(index=2, text="Gamma section."),
    ]
    document = ArtifactDocument(
        title="Draft",
        source_type=SourceType.TEXT,
        source_label="draft",
        text="\n\n".join(block.text for block in blocks),
        blocks=blocks,
        raw_content="Alpha section.\n\nBeta section.\n\nGamma section.",
    )
    anchor_gamma = ArtifactAnchor(block_id=blocks[2].id, start_offset=0, end_offset=5, quote="Gamma")
    anchor_alpha = ArtifactAnchor(block_id=blocks[0].id, start_offset=0, end_offset=5, quote="Alpha")
    artifact = AnalysisArtifact(
        source=ArtifactSource(source_type=SourceType.TEXT, source_label="draft"),
        document=document,
        run_config=RunConfig(selected_agents=["editorial"], runtime_mode=RuntimeMode.MOCK),
        anchors=[anchor_gamma, anchor_alpha],
    )
    accepted_gamma = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_gamma.id,
        author_type=AuthorType.AGENT,
        author_label="editorial agent",
        category=AgentCategory.EDITORIAL,
        body="Strengthen the gamma section.",
        suggestion="Move the gamma note earlier.",
        review_state=ReviewState.ACCEPTED,
    )
    accepted_alpha = ArtifactComment(
        artifact_id=artifact.artifact_id,
        anchor_id=anchor_alpha.id,
        author_type=AuthorType.AGENT,
        author_label="ai likelihood agent",
        category=AgentCategory.AI_LIKELIHOOD,
        body="Refine the alpha section.",
        suggestion="Trim the alpha claim.",
        review_state=ReviewState.ACCEPTED,
    )
    artifact.threads = [
        ArtifactThread(anchor=anchor_gamma, comments=[accepted_gamma]),
        ArtifactThread(anchor=anchor_alpha, comments=[accepted_alpha]),
    ]

    payload = build_revised_markdown_payload(artifact)
    revision_items = build_revision_suggestion_items(artifact)

    assert payload["original_markdown"] == document.raw_content
    accepted = payload["accepted_suggestions"]
    assert [item["quote"] for item in accepted] == ["Alpha", "Gamma"]
    assert accepted[0]["comment_id"] == accepted_alpha.id
    assert accepted[1]["comment_id"] == accepted_gamma.id
    assert [item.comment_id for item in revision_items] == [accepted_alpha.id, accepted_gamma.id]
