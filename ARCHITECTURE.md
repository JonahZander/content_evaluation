# Architecture Map

This project is an agent-readable monorepo with a Next.js frontend and a FastAPI backend. The system uses an artifact-first design: the backend produces a complete analysis artifact, the UI renders that artifact plus a live event stream, and persistence is an optional adapter rather than the center of the model.

## Top-Level Domains

- `docs/`
  - System of record for product, architecture, process, and plans
- `apps/web/`
  - Next.js review workbench for intake, live progress, artifact rendering, review actions, and import/export
- `services/api/`
  - FastAPI API, artifact orchestration, LangGraph execution, LangChain provider routing, repositories, and backend tests

## Layering

Frontend features should converge toward:

1. `types`
2. `lib`
3. `components/review`
4. `app`

Backend features should converge toward:

1. `domain`
2. `agents`
3. `providers/interfaces`
4. `providers/*`
5. `repositories`
6. `services`
7. `api`

## Runtime Architecture

- `apps/web`
  - `app/`
    - Next.js entrypoint and global styling
  - `src/components/ReviewWorkbench.tsx`
    - Top-level client coordinator for intake, live progress, artifact rendering, and review actions; uses `useReducer` for centralized state management
  - `src/components/review/`
    - Presentational review components: hero, toolbar, progress area, document pane, comment rail, summary panels, metrics, and selection composer
  - `src/components/review/workbench-state.ts`
    - Typed reducer, action union, and initial state for ReviewWorkbench
  - `src/lib/api.ts`
    - Browser API client for run creation, artifact fetch/import/export, replies, review state, and human comments
- `services/api`
  - `api/main.py`
    - FastAPI routes, health/readiness, artifact endpoints, SSE event stream, upload validation
  - `api/dependencies.py`
    - Long-lived service container, runtime mode selection, repository/provider wiring
  - `agents/`
    - Declarative agent registry and instruction files
  - `providers/`
    - LangChain-backed analysis routing for OpenAI, Anthropic, and Gemini with model caching; Tavily search, Trafilatura extraction, and mock fallback adapters with long-lived HTTP clients
  - `repositories/`
    - Session-first in-memory artifact storage and standalone PostgreSQL repository with Postgres-first writes, deepcopy cache isolation, and proper transactions
  - `services/`
    - Normalization, LangGraph orchestration, artifact assembly, review mutations, export building, bounded-concurrency worker loop

## Primary Architecture Decisions

- The API is the canonical producer of `AnalysisArtifact`.
- The UI renders artifact snapshots directly and does not depend on backend-only stitched view models.
- Live progress is a separate event stream, not the artifact itself.
- Session persistence is the default web workflow and requires no database.
- Session-mode runs and artifact export/import remain available for lightweight local and open-source use.
- LangChain owns model/provider abstraction for analysis agents.
- LangGraph owns orchestration/runtime flow for analysis runs.
- Artifact assembly stays in domain code and remains independent of LangGraph state.
- Multi-agent execution remains registry-driven:
  - one graph-backed orchestrator
  - a registry of specialist agents
  - explicit dependencies
  - parallel execution for independent agents
  - dependent execution for editorial and other prerequisite-driven follow-up steps

## Runtime Modes

- `session`
  - Default user-facing mode
  - No database required
  - Artifact and live events live in ephemeral backend/browser state
  - Export/import is the primary persistence mechanism
- `workspace`
  - Optional persisted mode that requires PostgreSQL
  - Stores artifact snapshots and review state in backend storage
  - Supports reopening prior runs
- `mock`
  - Default provider mode when live keys are absent
  - Uses deterministic local analysis/search/extraction providers
- `live`
  - Enabled when one configured analysis-provider key and Tavily are present
  - Uses LangChain-backed real analysis adapters plus real search/extraction providers

## Cross-Cutting Concerns

- artifact schema stability
- agent instructions and result schemas
- provider-family routing and model configuration
- dependency-driven orchestration
- graph checkpoints and restart recovery
- event streaming and debug traces
- optional persistence adapters
- export contracts

## Documentation Layout

- `docs/product/`
  - User problems, product goals, success criteria
- `docs/frontend/`
  - UI behaviors, progress timeline, review interactions, artifact import/export patterns
- `docs/backend/`
  - Pipelines, artifact contracts, Python standards, orchestration, summary assembly, and revised-markdown flow
- `docs/agents/`
  - Agent responsibilities, instructions, dependency graph, provider routing
- `docs/operations/`
  - Logging, traceability, readiness behavior, local/devops workflows
- `docs/process/`
  - Documentation hygiene, commit conventions, repo workflow
- `docs/plans/`
  - Active and completed execution plans

## Working Principle

The repository should expose enough structure that an agent can infer where to make a change without loading the entire knowledge base into context.
