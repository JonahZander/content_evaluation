# Analysis Pipeline

## Goal

Turn raw content into structured, explainable analysis that powers the review UI.

## Current Stages

1. Intake
   - Accept URL, uploaded `.txt`/`.md`, or pasted text
   - Validate upload type and size at the API boundary
2. Run creation
   - Create a queued run record
   - Persist a `run_job` for the background worker
3. Queued execution
   - `RunWorker` claims queued jobs
   - Resets in-flight jobs on startup
   - Requeues failed attempts up to the configured max attempts
2. Normalization
   - Extract text and metadata into a shared document schema
   - Split text into ordered document blocks
4. Agent execution
   - Similarity search
   - AI likelihood analysis
   - Value analysis
   - Audience analysis
   - Editorial analysis
   - Synthesis analysis
5. Anchor and comment generation
   - Convert excerpts into `TextAnchor` records
   - Persist agent findings and top-level agent comments per anchor
6. Aggregation
   - Compute novelty and AI-likelihood signals
   - Build `RunSummary`
7. Persistence and export
   - Store run metadata, events, comments, replies, and summary
   - Serve Markdown and JSON exports from persisted state

## Current Services

- `api/main.py`
  - HTTP routes, SSE event stream, upload validation, export endpoints
- `services/orchestration.py`
  - Run lifecycle, provider coordination, finding creation, summary scoring
- `services/worker.py`
  - Repository-backed polling worker
- `services/comments.py`
  - Human comment creation, reply creation, inline edit/delete checks, agent review-state updates
- `services/exporting.py`
  - Markdown and JSON export builders
- `repositories/in_memory.py`
  - Test and local fallback storage
- `repositories/postgres.py`
  - Async PostgreSQL persistence including `run_jobs`

## Boundaries

- Provider-specific details should live near adapters, not in orchestration logic.
- Shared document schemas should be stable and explicit.
- Aggregation should preserve evidence links back to spans and agent runs.
- Services should not contain raw SQL or raw provider HTTP calls.
- Production mode should not silently fall back to mock providers or in-memory storage.

## Public API Surface

- `POST /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events`
- `POST /api/v1/comments`
- `PATCH /api/v1/comments/{comment_id}`
- `DELETE /api/v1/comments/{comment_id}`
- `POST /api/v1/comments/{comment_id}/replies`
- `PATCH /api/v1/comments/{comment_id}/review-state`
- `GET /api/v1/runs/{run_id}/export.md`
- `GET /api/v1/runs/{run_id}/export.json`
- `GET /health`
- `GET /ready`
