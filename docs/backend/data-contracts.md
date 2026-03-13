# Data Contracts

This document describes the artifact schema as it exists in `domain/models.py`.
It is authoritative for agents writing code that reads or writes artifact data.

## AnalysisArtifact

The top-level output produced by the backend and rendered by the UI.

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `str` | Currently `"1.2"`. Bump when breaking changes are made to the export schema. |
| `artifact_id` | `UUID` | Stable identifier for the artifact. Used in all API routes and exports. |
| `status` | `RunStatus` | Current lifecycle state. See RunStatus transitions below. |
| `created_at` | `datetime` | UTC timestamp of artifact creation. |
| `updated_at` | `datetime` | UTC timestamp of last mutation. |
| `source` | `ArtifactSource` | Where the content came from. |
| `document` | `ArtifactDocument \| None` | Normalized content. `None` until normalization completes. |
| `run_config` | `RunConfig` | Agent selection, persistence mode, debug trace flag. |
| `agent_plan` | `list[ArtifactAgentPlanItem]` | Execution status of each agent. |
| `agent_results` | `list[ArtifactAgentResult]` | Structured output per agent. |
| `anchors` | `list[ArtifactAnchor]` | All text-range references produced by agents or humans. |
| `threads` | `list[ArtifactThread]` | Anchor → comments grouping. |
| `summary` | `ArtifactSummary \| None` | Aggregate scores. `None` until synthesis completes. |
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

### Why the legacy fields exist

`block_id`, `start_offset`, and `end_offset` at the anchor level were the original single-block anchor shape. `segments` was added to support multi-paragraph agent findings. A `model_validator` keeps the legacy fields in sync with `segments[0]` so older exports can still be imported correctly. Do not write code that assumes only one of these shapes is present — both are always populated.

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

## Export Schema Stability

- `schema_version` is `"1.2"`. Code that reads exported JSON should handle missing optional fields gracefully.
- `anchors[*].segments` is the canonical multi-block shape. `block_id`, `start_offset`, and `end_offset` at the anchor level are kept for backward compatibility and always mirror `segments[0]`.
- `ArtifactBlockOrigin.synthetic_unmatched` blocks are not original article text. Export consumers should exclude them or render them differently.
- `agent_results[*].raw_output` contains the unvalidated provider response. Do not rely on its shape externally.
- `debug` is always `null` unless `include_debug_trace: true` was set on the run.
