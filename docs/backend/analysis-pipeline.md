# Analysis Pipeline

## Goal

Turn raw content into a complete, explainable `AnalysisArtifact` that can be produced by the API independently of the frontend.

## Target Stages

1. Intake
   - Accept URL, uploaded `.txt`/`.md`, pasted text, and imported artifact JSON
   - Validate upload type and size at the API boundary
2. Session or workspace run creation
   - Create an artifact skeleton with run config, selected agents, and empty result slots
   - Persist a queued `run_job`
3. Queued execution
   - `RunWorker` claims queued jobs
   - Resets in-flight jobs on startup
   - Requeues failed attempts up to the configured max attempts
   - Starts or resumes LangGraph execution from the latest stored checkpoint
4. Normalization
   - Extract text and metadata into a shared document schema
   - Use direct fetch + Trafilatura first for URLs, then Tavily extract fallback for blocked or unreadable pages
   - Normalize markdown-aware content into ordered document blocks with render metadata and plain-text anchor offsets
   - Save the normalized document into the artifact
5. Agent planning
   - Validate selected agent ids
   - Expand required dependencies
   - Topologically sort the dependency graph
   - Record agent plan items with execution status
6. Agent execution
   - Run independent agents in parallel through LangGraph nodes
   - Run dependent agents after prerequisites complete
   - Emit progress events and partial artifact updates as each agent completes
   - Use LangChain chat-model adapters for analysis nodes
7. Artifact assembly
   - Convert agent outputs into anchors, comments, results, summary data, and debug traces
   - Resolve anchors against normalized block text, including whitespace-normalized and ellipsis-truncated excerpts when possible
   - Keep human comment/reply/review-state data in the same artifact structure
   - Keep artifact assembly outside the graph-state model
8. Export and import
   - Export the artifact as JSON
   - Export Markdown derived from the artifact
   - Reopen a saved artifact without rerunning the pipeline

## Artifact-First Rules

- `AnalysisArtifact` is the canonical backend output.
- `ArtifactDocument` preserves raw source content for rendering and normalized plain text for anchoring.
- The event stream narrates artifact construction; it is not the primary data model.
- Human comments, replies, and review-state changes live inside the artifact from the start.
- Persistence is an adapter around artifact snapshots, not the core business model.
- Backend services should be usable independently of the web app.
- `GraphRunState` is internal runtime state, not a public API contract.

## Current Refactor Direction

- `api/main.py`
  - HTTP routes, SSE event stream, upload validation, artifact endpoints
- `services/orchestration.py`
  - Session/workspace run lifecycle, LangGraph execution, dependency-driven scheduling, checkpoint persistence, artifact assembly
- `providers/langchain/client.py`
  - LangChain-backed provider routing across OpenAI, Anthropic, and Gemini
- `services/comments.py`
  - Human comment creation, reply creation, inline edit/delete checks, agent review-state updates against the artifact
- `services/exporting.py`
  - Artifact JSON and Markdown export builders
- `services/worker.py`
  - Repository-backed polling worker
- `agents/`
  - Declarative registry plus per-agent instruction files
- `repositories/`
  - Session-first storage with optional persisted artifact snapshots

## Boundaries

- Agent instructions belong in `agents/`, not inline inside provider code.
- Provider-specific details should live near adapters, not in orchestration logic.
- LangGraph state should stay smaller than the artifact contract.
- Shared artifact schemas should be stable and explicit.
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
- `POST /api/v1/artifacts/import`
- `GET /api/v1/runs/{run_id}/export.md`
- `GET /api/v1/runs/{run_id}/export.json`
- `GET /health`
- `GET /ready`
