# Data Contracts

This document describes the artifact schema as it exists in `domain/models.py`.
It is authoritative for agents writing code that reads or writes artifact data.

## AnalysisArtifact

The top-level output produced by the backend and rendered by the UI.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `str` | Currently `"1.4"`. Bump when breaking changes are made to the export schema. |
| `artifact_id` | `UUID` | Stable identifier for the artifact. Used in all API routes and exports. |
| `status` | `RunStatus` | Current lifecycle state. See RunStatus transitions below. |
| `created_at` | `datetime` | UTC timestamp of artifact creation. |
| `updated_at` | `datetime` | UTC timestamp of last mutation. |
| `source` | `ArtifactSource` | Where the content came from. |
| `document` | `ArtifactDocument \| None` | Normalized content. `None` until normalization completes. Includes the current `revision_id`. |
| `run_config` | `RunConfig` | Agent selection, persistence mode, debug trace flag. |
| `agent_plan` | `list[ArtifactAgentPlanItem]` | Execution status of each agent. |
| `agent_results` | `list[ArtifactAgentResult]` | Structured output per agent. |
| `anchors` | `list[ArtifactAnchor]` | All text-range references produced by agents or humans. |
| `threads` | `list[ArtifactThread]` | Anchor → comments grouping. |
| `summary` | `ArtifactSummary \| None` | Aggregate overview and score data. `None` until assembly completes. |
| `review_summary` | `ArtifactReviewSummary \| None` | Narrative review context for the panel above the text pane. Optional and backward-compatible. |
| `revised_document` | `ArtifactRevisedDocument \| None` | Candidate revised markdown generated after review-state acceptance, including revision mode and source revision provenance. |
| `diff_review` | `ArtifactDiffReview \| None` | Structured diff-review payload between canonical cleaner output and candidate revised markdown, including revision mode and source revision provenance. |
| `previous_draft_snapshot` | `ArtifactPreviousDraftSnapshot \| None` | Archived immediately previous draft used to preserve historical fact-check/research honestly after a revision apply. |
| `events` | `list[ArtifactEvent]` | Chronological run log for the SSE stream and UI timeline. |
| `debug` | `ArtifactDebug \| None` | Verbose trace data. Present only when `include_debug_trace` is true. |
| `error_message` | `str \| None` | Human-readable error description for failed runs. |

## RunStatus Transitions

```
draft → queued → running → completed
                         → failed
                         → canceled
```

| State | Triggered by |
|-------|-------------|
| `draft` | Artifact created from an import without queuing a job. |
| `queued` | Run job enqueued after `POST /api/v1/runs`. |
| `running` | Worker claims the job and calls the orchestrator. |
| `completed` | All selected agents finish successfully. |
| `failed` | Unrecoverable error after max retry attempts. |
| `canceled` | User stops the run via `POST /api/v1/runs/{run_id}/cancel`. |

## ArtifactBlock

One normalized paragraph, heading, or code block in the document.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable block identifier (e.g. `block-<uuid>`). Used in anchor references. |
| `index` | `int` | Zero-based position in the document block list. |
| `text` | `str` | Plain-text content used for anchoring and agent prompts. |
| `kind` | `ArtifactBlockKind` | `paragraph`, `heading`, or `code`. Default: `paragraph`. |
| `origin` | `ArtifactBlockOrigin` | `source` or `synthetic_unmatched`. |
| `markdown` | `str \| None` | Original markdown string when `content_format` is markdown. |
| `level` | `int \| None` | Heading level (1–6) when `kind` is `heading`. |
| `language` | `str \| None` | Language hint when `kind` is `code`. |
| `marks` | `list[ArtifactInlineMark]` | Inline formatting spans (strong, emphasis, code). |

## ArtifactDocument

The canonical normalized article after conservative pre-analysis cleaning.

| Field | Type | Description |
|-------|------|-------------|
| `revision_id` | `str` | Stable identifier for the current canonical draft revision. |
| `raw_content` | `str` | Cleaner-output markdown/plain text used as canonical analysis input. |
| `text` | `str` | Joined plain-text view of the normalized source blocks. |
| `blocks` | `list[ArtifactBlock]` | Reviewable source blocks after normalization and oversized-block splitting. |
| `cleaner_audit` | `ArtifactCleanerAudit \| None` | Removed and suspicious blocks preserved for audit/debug review. |

### ArtifactCleanerAudit

| Field | Type | Description |
|-------|------|-------------|
| `removed_blocks` | `list[ArtifactCleanerRemovedBlock]` | Blocks removed before analysis with original order and removal reason preserved. |
| `suspicious_blocks` | `list[ArtifactCleanerFlaggedBlock]` | Kept blocks flagged as suspicious or uncertain. |

### Cleaner removal reasons

- `site_chrome`
- `advertisement`
- `duplicate`
- `extraction_junk`
- `prompt_injection`
- `suspicious_non_article`

### ArtifactBlockOrigin values

| Value | Meaning |
|-------|---------|
| `source` | Block came from the original normalized source text. |
| `synthetic_unmatched` | Fallback block appended at document bottom when an agent excerpt could not be matched to any source block. Not original article content. |

## ArtifactAnchor

A text-range reference pointing into one or more adjacent document blocks.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Stable anchor identifier (e.g. `anchor-<uuid>`). |
| `document_revision_id` | `str \| None` | Revision the anchor originally belonged to. Historical preserved anchors keep the previous revision id even when they remap inline into the new draft. |
| `block_id` | `str` | Primary block ID. Mirrors `segments[0].block_id` for import compatibility. |
| `start_offset` | `int` | Char offset into the primary block's `text`. Mirrors `segments[0].start_offset`. |
| `end_offset` | `int` | Char offset end in the primary block. Mirrors `segments[0].end_offset`. |
| `quote` | `str` | The exact quoted text from the source. |
| `match_kind` | `ArtifactAnchorMatchKind` | `source` or `synthetic_unmatched`. |
| `segments` | `list[ArtifactAnchorSegment]` | Canonical multi-block shape. Always populated; legacy fields mirror `segments[0]`. |

### ArtifactAnchorSegment

One block-local slice within a multi-block anchor.

| Field | Type | Description |
|-------|------|-------------|
| `block_id` | `str` | Block containing this slice. |
| `start_offset` | `int` | Char offset start within that block's `text`. |
| `end_offset` | `int` | Char offset end within that block's `text`. |

### Anchor resolution rules

- Comment-producing agents should prefer a stable `block_id` plus an exact quoted excerpt.
- Backend resolution first searches the referenced block for an exact or ellipsis-normalized match.
- If exact matching fails, the backend may use a very small within-block fuzzy fallback before giving up on inline highlighting.
- When no source match is found, the anchor falls back to `synthetic_unmatched`.

### Why the legacy fields exist

`block_id`, `start_offset`, and `end_offset` at the anchor level were the original single-block anchor shape. `segments` was added to support multi-paragraph agent findings. A `model_validator` keeps the legacy fields in sync with `segments[0]` so older exports can still be imported correctly. Do not write code that assumes only one of these shapes is present — both are always populated.

## Revision Provenance

- `ArtifactComment.document_revision_id`, `ArtifactThread.document_revision_id`, `AgentFinding.document_revision_id`, and `ArtifactAgentResult.document_revision_id` identify which draft revision produced that finding surface.
- Current-revision workflows such as revised-markdown generation and summary building must scope to the active `document.revision_id`; preserved historical fact-check/research results are intentionally excluded from current-draft revision eligibility and current-draft summaries.
- Historical preserved results may still remain visible in the live artifact, but they are presentation-only context unless a caller explicitly asks for archived previous-draft data.

## ArtifactEvent

One durable event appended to the artifact during a run. Narrates run lifecycle, agent progress, and errors.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Event identifier. |
| `artifact_id` | `UUID` | Owning artifact. |
| `event_type` | `EventType` | `run`, `artifact`, or `agent`. |
| `stage` | `str` | Short label for the pipeline stage (e.g. `normalization`, `similarity`). |
| `message` | `str` | Human-readable description. |
| `status` | `str` | Stage status string (e.g. `started`, `completed`, `failed`, `resumed`). |
| `progress` | `float \| None` | 0.0–1.0 overall progress. Present on run-level events. |
| `agent_id` | `str \| None` | Agent that emitted this event, if applicable. |
| `model_name` | `str \| None` | LLM model name used, if applicable. |
| `attempt` | `int \| None` | Retry attempt number, if applicable. |
| `error_kind` | `str \| None` | Structured error category from the provider layer. |
| `snapshot_available` | `bool` | When true, the UI should refetch the artifact to get updated state. |

### EventType values

| Value | When emitted |
|-------|-------------|
| `run` | Run lifecycle transitions (queued, running, completed, failed, canceled, resumed). |
| `artifact` | Artifact-level milestones (normalization done, document saved). |
| `agent` | Per-agent start, completion, retry, and failure events. |

## ArtifactReviewSummary

Narrative review context shown above the source text pane.

| Field | Type | Description |
|-------|------|-------------|
| `content_summary` | `str` | Backward-compatible content summary; now usually mirrors `tl_dr`. |
| `research_summary` | `str` | Fact-check-backed research summary. |
| `tl_dr` | `str` | Top-level concise article summary. |
| `inferred_audience` | `str` | Audience inference shown as summary text. |
| `word_count` | `int` | Word count based on source blocks. |
| `estimated_reading_time_minutes` | `int` | Estimated reading time from the canonical cleaner output. |
| `article_format` | `str` | Heuristic article-type guess such as `tutorial`, `announcement`, or `case_study`. |
| `reading_difficulty` | `str` | Coarse density indicator such as `accessible`, `moderate`, or `dense`. |
| `structural_completeness` | `ArtifactStructuralCompleteness` | Lightweight intro/headings/conclusion signals. |
| `main_claims` | `list[ArtifactClaimSummary]` | Legacy fact-check claim summary kept for import compatibility; the UI no longer renders it by default. |
| `overlap_items` | `list[ArtifactOverlapItem]` | Linked overlapping articles with short notes. |

### ArtifactOverlapItem

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Linked article title. |
| `url` | `str` | URL for the overlapping article. |
| `note` | `str` | Short explanation of why the article overlaps. |

### ArtifactClaimSummary

Legacy claim summary shape retained for compatibility with older exports and imports. New fact-check UI should read thread-level comment metadata instead.

| Field | Type | Description |
|-------|------|-------------|
| `claim_text` | `str` | Main claim or fact being assessed. |
| `verdict` | `str` | Fact-check verdict such as `SUPPORTED` or `MIXED`. |
| `evidence_summary` | `str` | Short explanation of what the research found. |
| `source_links` | `list[str]` | Links relevant to the claim. |
| `anchor_quote` | `str` | Quoted article text tied to the claim. |
| `value_add` | `str` | How the article still adds value or differentiation on this claim. |
| `official_source_links` | `list[str]` | Preferred primary or official supporting links. |
| `related_post_links` | `list[str]` | Related-post links tied to the claim/topic. |

## RunInput

The queued request payload used by the worker and API routes.

| Field | Type | Description |
|-------|------|-------------|
| `mode` | `RunMode` | `create`, `append_agents`, or `research`. |
| `prompt` | `str \| None` | Targeted research prompt used by `POST /api/v1/runs/{run_id}/research`. |
| `anchor_id` | `str \| None` | Optional anchor identifier for scoping targeted research. |
| `comment_id` | `str \| None` | Optional comment identifier; when present, the follow-up prompt is stored as a reply before the research job is queued. |
| `selected_agents` | `list[str]` | Agent ids for the queued run. Research uses the dedicated non-selectable `research` agent. |

- `AgentCategory.research` is used for threaded targeted-research findings.
- Research runs append to the existing artifact and do not replace previous fact-check findings.

## Revised Markdown Contracts

- `ArtifactRevisedDocument` stores the generated candidate markdown plus the accepted comment ids that informed it, the explicit revision `mode`, the `source_revision_id`, and an optional rewrite `direction_prompt`.
- `ArtifactDiffReview` stores the same revision provenance plus `original_markdown`, `candidate_markdown`, and `diff_items`.
- `ArtifactPreviousDraftSnapshot` stores the archived prior `document`, its preserved `anchors`, preserved fact-check/research `threads`, preserved fact-check/research `agent_results`, and the archived `document_revision_id`.
- Each `ArtifactDiffItem` carries a `change_type`, `before_text`, `after_text`, and reviewer `decision`.
- Diff items also preserve original and candidate line ranges so selective application can rebuild the next working markdown deterministically.
- Applying reviewed diffs promotes a newly normalized document, preserves only historical fact-check/research context from the immediately previous draft, and leaves the artifact ready for a follow-up analysis run on the revised draft.

## Export Schema Stability

- `schema_version` is `"1.4"`. Code that reads exported JSON should handle missing optional fields gracefully.
- `review_summary` is optional. Older exports may omit it entirely.
- `document.cleaner_audit` is optional. Older exports may omit it entirely.
- `revised_document` and `diff_review` are optional. Older exports may omit them entirely.
- `anchors[*].segments` is the canonical multi-block shape. `block_id`, `start_offset`, and `end_offset` at the anchor level are kept for backward compatibility and always mirror `segments[0]`.
- `ArtifactBlockOrigin.synthetic_unmatched` blocks are not original article text. Export consumers should exclude them or render them differently.
- `agent_results[*].raw_output` contains the unvalidated provider response. Do not rely on its shape externally.
- Fact-check evidence used by the UI lives on `agent_results[*].findings[*].metadata` and on the corresponding threaded `ArtifactComment.metadata`, especially `claim_text`, `verdict`, `evidence_summary`, `source_links`, `official_source_links`, and `related_post_links`.
- `debug` is always `null` unless `include_debug_trace: true` was set on the run.
