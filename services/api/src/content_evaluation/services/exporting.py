"""Run export helpers."""

from __future__ import annotations

import json

from content_evaluation.domain.models import Comment, CommentThread, RunDetail


def build_markdown_export(detail: RunDetail) -> str:
    """Render one run as Markdown."""

    if detail.document is None:
        return "# Empty run\n"

    body = [f"# {detail.document.title}", "", detail.document.text, "", "## Comments", ""]
    for thread in detail.threads:
        body.extend(_render_thread(thread))
    return "\n".join(body).strip() + "\n"


def build_json_export(detail: RunDetail) -> str:
    """Render one run as stable JSON."""

    return json.dumps(
        {
            "document": detail.document.model_dump(mode="json") if detail.document else None,
            "anchors": [anchor.model_dump(mode="json") for anchor in detail.anchors],
            "threads": [thread.model_dump(mode="json") for thread in detail.threads],
            "findings": [finding.model_dump(mode="json") for finding in detail.findings],
            "summary": detail.summary.model_dump(mode="json") if detail.summary else None,
            "run_metadata": detail.run.model_dump(mode="json"),
            "events": [event.model_dump(mode="json") for event in detail.events],
        },
        indent=2,
    )


def _render_thread(thread: CommentThread) -> list[str]:
    """Render one comment thread as Markdown."""

    lines = [f"### {thread.anchor.quote}", ""]
    for comment in thread.comments:
        lines.extend(_render_comment(comment))
    return lines


def _render_comment(comment: Comment) -> list[str]:
    """Render one top-level comment as Markdown."""

    lines = [
        f"- [{comment.category.value}] {comment.author_label}: {comment.body}",
        f"  - Review state: {comment.review_state.value}",
    ]
    if comment.suggestion:
        lines.append(f"  - Suggestion: {comment.suggestion}")
    for reply in comment.replies:
        lines.append(f"  - Reply ({reply.author_label}): {reply.body}")
    return lines
