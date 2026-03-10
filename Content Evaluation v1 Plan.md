# Content Evaluation v1 Plan

## Summary

Build the first real implementation as a two-part monorepo:

- `apps/web`: Next.js review application with a split-pane annotation UI
- `services/api`: FastAPI + PostgreSQL backend in Python 3.12

Default live provider stack will be OpenAI for structured agent analysis and Tavily for web similarity search, with explicit provider interfaces so adapters can be replaced later without rewriting service logic.

The v1 review experience will use one shared reviewer identity, real persisted runs/comments in Postgres, export in Markdown and JSON, Docker deployment support, and local non-Docker development for both web and API.

## Key Changes

### Repository and knowledge base

- Update the repo map to a clear frontend/backend split and document the default runtime as `apps/web` + `services/api`.
- Add backend knowledge distilled from your Python standards:
  - Python 3.12
  - PEP8
  - max line length 120
  - snake_case
  - type hints on all public functions
  - Pydantic validation at module boundaries
  - docstrings on all functions and methods
  - strict provider/repository/service layering
  - provider-agnostic and storage-agnostic service contracts
  - typed exceptions, structured logs, pytest, docs updated with behavior changes
- Add `services/api/pyproject.toml` with FastAPI/Python runtime deps plus Ruff, mypy, and pytest config aligned to those standards.
- Extend the frontend and backend docs to cover:
  - left-text/right-comments review layout
  - connector lines and shared anchor threads
  - reviewer responses to agent comments
  - export behavior
  - Docker and local development workflows

### Backend implementation

- Use FastAPI with explicit layers:
  - `domain`: shared models and typed exceptions
  - `providers/interfaces`: protocols for LLM analysis, similarity search, and content extraction
  - `providers/openai` and `providers/tavily`: default live adapters
  - `repositories/postgres`: SQL-only persistence using `psycopg` and pooling
  - `services`: orchestration, scoring, exports, review actions
  - `api`: request/response validation and transport
- Normalize all inputs into one document model:
  - URL input via article extraction
  - uploaded `.txt` and `.md`
  - pasted raw text
- Use text-range anchors as the core review primitive:
  - `TextAnchor`: `id`, `block_id`, `start_offset`, `end_offset`, `quote`
  - all comments attach to one anchor
  - multiple comments on one anchor become one thread in the right rail
- Persist the minimum stable entities:
  - `documents`
  - `document_blocks`
  - `analysis_runs`
  - `run_events`
  - `anchors`
  - `comments`
  - `comment_replies`
- Support two comment author types:
  - `agent`
  - `human`
- Support comment-level review state for agent comments:
  - `accepted`
  - `rejected`
  - `uncertain`
  - default `unreviewed`
- Human reviewers can add threaded replies to any agent comment and to other human comments.
- Human reviewers can create standalone comments on selected text ranges.
- Agent comments are immutable in body/content; human input is captured as replies and review-state actions.
- Run the analysis pipeline asynchronously, persist step-by-step progress, and expose live updates through SSE.
- Keep providers replaceable via service-facing protocols such as:
  - `SimilaritySearchProvider`
  - `AnalysisModelProvider`
  - `ContentExtractionProvider`
  - `RunRepository`
- Implement structured outputs for:
  - similarity agent
  - AI-likelihood agent
  - value agent
  - audience agent
  - editorial agent
  - synthesis agent

### Review UI and interaction model

- Build the main page as a split-pane editorial workspace:
  - left: normalized article text
  - right: threaded comments attached to anchors
  - top summary strip: overall score, per-agent findings, run status, export actions
- Use one shared vertical scroll context for text and comments.
- Render connectors with a full-page SVG overlay spanning both columns.
- Measure text anchor rects and thread/comment card rects on layout, scroll, and resize, then draw connector paths between them.
- Group comments by anchor in the right rail; within a thread, cards stack vertically in one column.
- If multiple comments target the same anchor, all cards remain stacked in the same thread and each card connects to the same highlighted text range.
- Add hover/focus linking in both directions:
  - hover comment or reply highlights anchor
  - hover anchor highlights thread
- For each top-level agent comment card, show three immediate reviewer actions:
  - `Accept`
  - `Reject`
  - `Uncertain`
- Review action buttons update only the review state of that agent comment; they do not alter the original agent text.
- Each top-level comment card also supports human discussion:
  - inline reply composer
  - visible reply thread underneath the parent comment
  - shared reviewer identity label on human replies
- Human-created standalone comments also render in the same right-rail thread model, but only human comments are editable/deletable.
- Highlight system:
  - category-based colors for agent types
  - neutral shared highlight for multi-comment anchors with visible side markers for multiple categories
  - reviewed state badge on each agent comment showing `accepted`, `rejected`, `uncertain`, or `unreviewed`
- Visual direction:
  - editorial-review aesthetic
  - light paper-like base, dark ink typography, saturated analysis accents
  - non-generic typography pairing and deliberate motion, consistent with the frontend-design skill

### Exports and deployment

- Add export services derived from persisted run data, not recomputed from providers:
  - Markdown export
  - JSON export
- Markdown export format:
  - normalized text first in reading order
  - appended `Comments` section at the end
  - comments grouped by anchor/thread
  - include anchor quote or reference, author type, agent/category if applicable, review state, and replies
- JSON export format:
  - stable schema including `document`, `blocks`, `anchors`, `comments`, `replies`, `threads`, `summary`, and `run_metadata`
- Add export UI actions:
  - `Export Markdown`
  - `Export JSON`
- Containerization:
  - `Dockerfile` for web
  - `Dockerfile` for API
  - `docker-compose.yml` for web + API + Postgres
- Local development remains first-class:
  - run Next.js locally
  - run FastAPI locally
  - connect to local or containerized Postgres
  - `.env`-based config for both Docker and non-Docker workflows

## Public Interfaces and Types

- `POST /api/v1/runs`
  - create a run from URL, file, or pasted text and start analysis
- `GET /api/v1/runs/{run_id}`
  - return normalized document, anchors, grouped comments, replies, summary, and run metadata
- `GET /api/v1/runs/{run_id}/events`
  - SSE stream of run progress and agent/model events
- `POST /api/v1/comments`
  - create a human standalone comment on an anchor
- `PATCH /api/v1/comments/{comment_id}`
  - edit a human standalone comment
- `DELETE /api/v1/comments/{comment_id}`
  - delete a human standalone comment
- `POST /api/v1/comments/{comment_id}/replies`
  - add a human reply to an existing comment
- `PATCH /api/v1/comments/{comment_id}/review-state`
  - set agent comment review state to `accepted`, `rejected`, or `uncertain`
- `GET /api/v1/runs/{run_id}/export.md`
  - return Markdown export
- `GET /api/v1/runs/{run_id}/export.json`
  - return JSON export

Stable domain types:

- `NormalizedDocument`
- `DocumentBlock`
- `TextAnchor`
- `Comment`
- `CommentReply`
- `CommentThread`
- `AgentFinding`
- `RunSummary`
- `RunEvent`

## Test Plan

- Backend unit tests:
  - provider parameter serialization and error mapping
  - retry behavior for transient failures
  - anchor generation and thread grouping
  - review-state transitions for agent comments
  - reply creation rules and export serialization
  - scoring/synthesis from structured agent outputs
- Backend repository tests:
  - create/read runs
  - upsert anchors/comments
  - persist replies and review-state changes
  - event persistence and ordering
- Backend API tests:
  - ingestion for URL, file, and pasted text
  - SSE event stream
  - human standalone comment create/edit/delete
  - human reply creation on agent and human comments
  - accept/reject/uncertain actions on agent comments
  - Markdown and JSON export responses
- Frontend component/integration tests:
  - anchor highlighting and connector rendering
  - multiple comments on one anchor stack and connect correctly
  - reply thread renders under the parent comment
  - accept/reject/uncertain buttons update visible state
  - selecting text creates a human standalone comment
  - hovering a comment or reply focuses the linked text span
- End-to-end tests:
  - submit content, watch run progress, inspect agent comments, reply to one, mark one accepted/rejected/uncertain, export Markdown and JSON, refresh, and confirm persistence
  - boot the Docker stack and verify service connectivity
  - run web and API locally without Docker and verify equivalent behavior

## Assumptions and Defaults

- FastAPI is the Python backend framework.
- OpenAI and Tavily are the first concrete adapters, but all business logic depends on provider interfaces.
- v1 supports URL input, pasted text, and uploaded `.txt`/`.md` files only.
- v1 uses one shared reviewer identity and does not add full user auth yet.
- Agent comments are immutable in content; human reviewers interact through replies and review-state actions.
- Human standalone comments are editable/deletable; replies may be editable in v1 only if authored by the shared reviewer, using the same human-comment rules.
- Analysis runs are asynchronous and durable, but v1 does not introduce a separate external queue system yet.
- The article text is review-only in v1; users annotate it but do not directly edit the source text inside the app.
