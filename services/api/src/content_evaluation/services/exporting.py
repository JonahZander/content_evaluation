"""Artifact export helpers."""

from __future__ import annotations

import json

from content_evaluation.domain.models import AnalysisArtifact, ArtifactComment, ArtifactThread


def build_markdown_export(artifact: AnalysisArtifact) -> str:
    """Render one artifact as Markdown."""

    if artifact.document is None:
        return "# Empty artifact\n"

    body = [f"# {artifact.document.title}", "", artifact.document.text, "", "## Comments", ""]
    for thread in artifact.threads:
        body.extend(_render_thread(thread))
    if artifact.debug and artifact.debug.traces:
        body.extend(["", "## Debug Trace", ""])
        for trace in artifact.debug.traces:
            body.append(f"- {json.dumps(trace, ensure_ascii=True)}")
    return "\n".join(body).strip() + "\n"


def build_json_export(artifact: AnalysisArtifact) -> str:
    """Render one artifact as stable JSON."""

    return json.dumps(artifact.model_dump(mode="json"), indent=2)


def _render_thread(thread: ArtifactThread) -> list[str]:
    """Render one comment thread as Markdown."""

    lines = [f"### {thread.anchor.quote}", ""]
    for comment in thread.comments:
        lines.extend(_render_comment(comment))
    return lines


def _render_comment(comment: ArtifactComment) -> list[str]:
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
