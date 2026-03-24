# Analysis Pipeline

## Goal

Turn raw content into a complete, explainable `AnalysisArtifact` that can be produced by the API independently of the frontend.

## Target Stages

1. Intake
   - Accept URL, uploaded `.txt`/`.md`, pasted text, and imported artifact JSON
   - Support source preview for URL imports before a run is queued
   - Validate upload type and size at the API boundary
2. Session or workspace run creation
   - Create an artifact skeleton with run config, selected agents, and empty result slots
   - URL preview runs may submit a reviewer-pruned markdown draft derived from visible preview blocks instead of re-fetching the original URL content
   - Persist a queued `run_job`
   - Terminal artifacts may queue additive follow-up analysis that reuses the existing document and completed findings
3. Queued execution
   - `RunWorker` claims queued jobs
   - `RunWorker` delegates claimed jobs to `RunOrchestrator.process_run()`
   - Resets in-flight jobs on startup
   - Requeues failed attempts up to the configured max attempts only for worker/process recovery
   - Cancels queued or active jobs when the user stops a run
   - Routes each job through one of three execution paths:
     - append-agent runs reuse the existing normalized document and only execute newly requested agents
     - `langgraph` runs start or resume LangGraph execution from the latest stored checkpoint
     - `legacy` runs execute the older batch loop without LangGraph checkpoints
4. Normalization
   - Extract text and metadata into a shared document schema
   - Use direct fetch + Trafilatura markdown extraction first for URLs, then Tavily extract fallback for blocked or unreadable pages
   - Run a conservative pre-analysis cleaner before the document becomes canonical analysis input
   - Remove obvious site chrome, ad/promotional blocks, extraction junk, prompt-injection text, and exact duplicate remnants
   - Keep uncertain blocks by default and record both removed and suspicious blocks in `ArtifactDocument.cleaner_audit`
   - Treat the cleaner output as the canonical `raw_content` used by downstream analysis
   - Normalize markdown-aware content into ordered document blocks with render metadata, inline link marks, and plain-text anchor offsets
   - Conservatively split oversized plain-text paragraph blocks so collapsed imports do not become one giant review span
   - Save the normalized document into the artifact
5. Agent planning
   - Validate selected agent ids
   - Expand required dependencies
   - Topologically sort the dependency graph
   - Record agent plan items with execution status
   - Completed fact-check stays visible in the UI as a locked option, but append-agents still filters it out so it cannot be rerun once an artifact has fact-check results
6. Agent execution
  - Run independent agents in parallel through LangGraph nodes
  - Run dependent agents after prerequisites complete
  - Default graph now uses fact-check as the research backbone:
    - `fact_check` and `ai_likelihood` can start independently
    - `editorial` depends on `fact_check` and `ai_likelihood`
  - `value`, `audience`, and first-pass `synthesis` are no longer scheduled in the main run
  - Retry transient provider timeouts and network failures inside the individual agent execution loop before failing the run
   - Emit progress events and partial artifact updates as each agent completes
   - Capture token usage (`input_tokens`, `output_tokens`) in `AgentExecutionResult.usage` after each LLM call; populated by the LangChain, deep research, and mock providers
   - Use LangChain chat-model adapters for analysis nodes
   - Require comment-producing agents to return exact quoted excerpts, prefer stable `block_id` references, use ellipses only for real omissions, and split evidence that would span more than 3 paragraphs into multiple findings
7. Artifact assembly
  - Convert agent outputs into anchors, comments, results, summary data, debug traces, and usage metadata
  - Build both score-oriented `summary` data and narrative `review_summary` data
  - Thread `AgentExecutionResult.usage` into `ArtifactAgentResult.metadata` so token counts are available to the frontend without re-querying backend state
   - Resolve comment anchors against normalized block text, preferring exact matches inside the referenced `block_id` and using a bounded within-block fuzzy fallback only for near-miss quotes
   - Treat ellipsis excerpts as ordered fragments across one source block or a bounded window of adjacent source blocks instead of collapsing them into one normalized string
   - Represent resolved anchors as ordered block-local segments so one finding can span multiple adjacent paragraphs
   - Exclude synthetic unmatched fallback blocks from later anchor matching and downstream agent context
   - When an excerpt still cannot be mapped into adjacent visible blocks, append a bottom-of-document unmatched-reference block instead of falling back to the first paragraph
  - Keep human comment/reply/review-state data in the same artifact structure
  - Keep fact-check claim evidence on structured finding metadata so the frontend can render nearby evidence links without parsing prose
  - Fact-check is now summary-first and also supplies TL;DR, audience overview, main-claim summaries, official-source links, and differentiation/value context
  - AI-likelihood and editorial remain the only default comment-producing agents in new runs
  - Keep artifact assembly outside the graph-state model
8. Export and import
   - Export the artifact as JSON
   - Export Markdown derived from the artifact
   - Export accepted agent suggestions as a compact Markdown todo list ordered by source position, including both the agent comment text and the suggestion
   - Generate candidate revised markdown only after accepted suggestions exist
   - Compute diff-review items deterministically from whole-document markdown comparison
   - Replace the canonical markdown only after reviewed diff decisions are applied
   - Reopen a saved artifact without rerunning the pipeline

## Artifact-First Rules

- `AnalysisArtifact` is the canonical backend output.
- `ArtifactDocument` preserves raw source content for rendering and normalized plain text for anchoring.
- `ArtifactBlock.origin` distinguishes real source blocks from synthetic unmatched fallback blocks.
- `ArtifactAnchor.segments` is the canonical anchor shape; legacy single-block fields remain import-compatible.
- The event stream narrates artifact construction; it is not the primary data model.
- Human comments, replies, and review-state changes live inside the artifact from the start.
- Persistence is an adapter around artifact snapshots, not the core business model.
- Backend services should be usable independently of the web app.
- `GraphRunState` is internal runtime state, not a public API contract.
- `ArtifactEvent` is the public place to surface run retries, worker resumptions, and provider failure metadata to the UI.

## Orchestration Backend Selection

- `OrchestratorBackend.LANGGRAPH` is the default backend and drives new full-run execution.
- `OrchestratorBackend.LEGACY` remains available as a compatibility path for the older batch executor.
- Additive follow-up analysis does not use the full-run backend switch; it routes through the dedicated append-agents path.
- The active backend is configured through `Settings.orchestrator_backend` and is surfaced in readiness output.

## Current Implementation Notes

- `api/main.py`
  - HTTP routes, SSE event stream (with configurable timeout), upload validation, artifact endpoints
- `api/dependencies.py`
  - Long-lived service container; `AppServices.stop()` closes provider HTTP clients on shutdown
- `services/orchestration.py`
  - Session/workspace run lifecycle, backend selection (`append_agents`, `langgraph`, or `legacy`), dependency-driven scheduling, checkpoint persistence, and artifact assembly
- `providers/langchain/client.py`
  - LangChain-backed provider routing across OpenAI, Anthropic, and Gemini
  - Chat models are cached per (family, model_name) pair for the lifetime of the provider
- `providers/tavily/client.py`
  - Tavily search with a shared `httpx.AsyncClient` created at startup
- `providers/extraction/client.py`
  - Trafilatura and Tavily extraction providers each hold a long-lived `httpx.AsyncClient`
  - `FallbackExtractionProvider.close()` delegates to both inner providers
- `services/comments.py`
  - Human comment creation, reply creation/deletion, inline edit/delete checks, agent review-state updates against the artifact
  - Comment and reply lookup uses the `list_artifact_ids()` repository protocol method to work with both in-memory and Postgres backends
- `services/exporting.py`
  - Artifact JSON, Markdown, and compact todo export builders
- `services/worker.py`
  - Repository-backed polling worker that claims queued jobs, delegates execution to the orchestrator, and enforces bounded concurrency (`worker_max_concurrent_runs` setting, `asyncio.Semaphore`)
  - `stop()` drains in-flight tasks before shutting down
- `agents/`
  - Declarative registry plus per-agent instruction files
- `repositories/`
  - Session-first in-memory storage; standalone PostgreSQL repository (no `InMemoryRunRepository` inheritance)
  - Postgres backend uses `psycopg_pool.AsyncConnectionPool` for connection reuse
  - Write path: Postgres first, cache on success; read path: cache first with `deepcopy` isolation
  - All writes wrapped in `connection.transaction()` blocks

## Boundaries

- Agent instructions belong in `agents/`, not inline inside provider code.
- Provider-specific details should live near adapters, not in orchestration logic.
- LangGraph state should stay smaller than the artifact contract.
- Shared artifact schemas should be stable and explicit.
- Services should not contain raw SQL or raw provider HTTP calls.
- Production mode should not silently fall back to mock providers or in-memory storage.

## Public API Surface

- `GET /api/v1/agents`
- `POST /api/v1/runs`
- `POST /api/v1/runs/{run_id}/agents`
- `POST /api/v1/sources/preview`
- `GET /api/v1/runs/{run_id}`
- `POST /api/v1/runs/{run_id}/cancel`
- `POST /api/v1/runs/{run_id}/revised-markdown`
- `PATCH /api/v1/runs/{run_id}/revised-markdown/diff-review`
- `POST /api/v1/runs/{run_id}/revised-markdown/apply`
- `GET /api/v1/runs/{run_id}/events`
- `POST /api/v1/comments`
- `PATCH /api/v1/comments/{comment_id}`
- `DELETE /api/v1/comments/{comment_id}`
- `POST /api/v1/comments/{comment_id}/replies`
- `DELETE /api/v1/replies/{reply_id}`
- `PATCH /api/v1/comments/{comment_id}/review-state`
- `POST /api/v1/artifacts/import`
- `GET /api/v1/runs/{run_id}/export.md`
- `GET /api/v1/runs/{run_id}/export.json`
- `GET /api/v1/runs/{run_id}/export.todo.md`
- `GET /health`
- `GET /ready`
