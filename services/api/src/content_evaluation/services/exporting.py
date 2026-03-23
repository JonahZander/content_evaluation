"""Artifact export helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from content_evaluation.domain.models import (
    AnalysisArtifact,
    ArtifactAnchor,
    ArtifactComment,
    ArtifactThread,
)


@dataclass(frozen=True)
class _TodoItem:
    """Store one accepted suggestion ready for todo export."""

    quote: str
    comment: str
    suggestion: str
    author_label: str
    unmatched: bool
    sort_key: tuple[int, int, int, str, datetime, str]


@dataclass(frozen=True)
class RevisionPayloadItem:
    """Store one accepted suggestion for revision payload generation."""

    comment_id: str
    quote: str
    comment: str
    suggestion: str
    author_label: str
    unmatched: bool
    sort_key: tuple[int, int, int, str, datetime, str]


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


def build_todo_export(artifact: AnalysisArtifact) -> str:
    """Render accepted agent suggestions as a compact Markdown todo list."""

    if artifact.document is None:
        return "# Empty artifact\n"

    items = _revision_items(artifact)
    lines = [f"# {artifact.document.title} Revision Todo", ""]
    if not items:
        lines.extend(["## Revision Todo", "", "- No accepted agent suggestions yet.", ""])
        return "\n".join(lines)

    lines.extend(["## Revision Todo", ""])
    for item in items:
        lines.append(f'- [ ] "{item.quote}"')
        lines.append(f"  Note: {item.comment}")
        lines.append(f"  {item.suggestion}")
    lines.extend(["", "## Context", ""])
    for index, item in enumerate(items, start=1):
        lines.append(f'### {index}. "{item.quote}"')
        lines.append(f"- Comment: {item.comment}")
        lines.append(f"- Suggestion: {item.suggestion}")
        lines.append(f"- Agent: {item.author_label}")
        if item.unmatched:
            lines.append("- Anchor: unmatched synthetic fallback")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_revised_markdown_payload(artifact: AnalysisArtifact) -> dict[str, object]:
    """Return deterministic accepted-suggestion payload data for revised markdown generation."""

    if artifact.document is None:
        return {"original_markdown": "", "accepted_suggestions": []}

    items = _revision_items(artifact)
    return {
        "original_markdown": artifact.document.raw_content or artifact.document.text,
        "accepted_suggestions": [
            {
                "comment_id": item.comment_id,
                "quote": item.quote,
                "comment": item.comment,
                "suggestion": item.suggestion,
                "author_label": item.author_label,
                "unmatched": item.unmatched,
            }
            for item in items
        ],
    }


def build_revision_suggestion_items(artifact: AnalysisArtifact) -> list[RevisionPayloadItem]:
    """Return accepted revision items in article order for callers that need stable ordering."""

    return _revision_items(artifact)


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


def _revision_items(artifact: AnalysisArtifact) -> list[RevisionPayloadItem]:
    """Return accepted agent suggestions in stable article order."""

    block_index_by_id = {
        block.id: block.index for block in (artifact.document.blocks if artifact.document is not None else [])
    }
    items: list[RevisionPayloadItem] = []
    for thread in artifact.threads:
        for comment in thread.comments:
            if comment.author_type.value != "agent":
                continue
            if comment.review_state.value != "accepted" or not comment.suggestion:
                continue
            items.append(
                RevisionPayloadItem(
                    comment_id=comment.id,
                    quote=_compact_text(thread.anchor.quote),
                    comment=_compact_text(comment.body),
                    suggestion=_compact_text(comment.suggestion),
                    author_label=comment.author_label,
                    unmatched=thread.anchor.match_kind.value == "synthetic_unmatched",
                    sort_key=_todo_sort_key(thread.anchor, comment, block_index_by_id),
                )
            )
    items.sort(key=lambda item: item.sort_key)
    return items


def _todo_sort_key(
    anchor: ArtifactAnchor,
    comment: ArtifactComment,
    block_index_by_id: dict[str, int],
) -> tuple[int, int, int, str, datetime, str]:
    """Return a deterministic sort key for one todo item."""

    primary_segment = anchor.segments[0]
    unmatched = 1 if anchor.match_kind.value == "synthetic_unmatched" else 0
    block_index = block_index_by_id.get(primary_segment.block_id, 10**9)
    return (
        unmatched,
        block_index,
        primary_segment.start_offset,
        anchor.id,
        comment.created_at,
        comment.id,
    )


def _compact_text(value: str) -> str:
    """Collapse whitespace for compact export output."""

    return " ".join(value.split())
