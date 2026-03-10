# Architecture Map

This project is implemented as an agent-readable monorepo with a Next.js frontend and a FastAPI backend.

## Top-Level Domains

- `docs/`
  - System of record for product, architecture, process, and plans
- `apps/web/`
  - Next.js routes, review workbench UI, export actions, and Vitest coverage
- `services/api/`
  - FastAPI API, provider adapters, repositories, orchestration services, durable worker loop, and backend tests
- `.codex/skills/`
  - Repo-local skills for recurring agent workflows

## Layering

Frontend features should converge toward:

1. `types`
2. `lib`
3. `components/review`
4. `app`

Backend features should converge toward:

1. `domain`
2. `providers/interfaces`
3. `providers/*`
4. `repositories`
5. `services`
6. `api`

## Runtime Architecture

- `apps/web`
  - `app/`
    - Next.js entrypoint and global styling
  - `src/components/ReviewWorkbench.tsx`
    - Top-level client coordinator for intake, live refresh, and review actions
  - `src/components/review/`
    - Presentational review components: hero, toolbar, document pane, comment rail, metrics, selection composer, connector overlay
  - `src/lib/api.ts`
    - Browser API client for runs, comments, replies, review state, and exports
- `services/api`
  - `api/main.py`
    - FastAPI routes, `/health`, `/ready`, SSE event stream, upload validation
  - `api/dependencies.py`
    - Long-lived service container, runtime mode selection, repository/provider wiring
  - `providers/`
    - OpenAI analysis adapter, Tavily similarity search adapter, Trafilatura extraction adapter, mock fallback adapters for local development
  - `repositories/`
    - In-memory repository and PostgreSQL repository with `run_jobs` persistence
  - `services/orchestration.py`
    - Run creation, normalization, agent execution, summary scoring, comment generation
  - `services/worker.py`
    - Polling worker that claims queued jobs and drives analysis outside the request/response path

## Runtime Modes

- `mock`
  - Default for local development when provider keys are absent
  - Uses mock analysis/search/extraction providers
  - Keeps the UI and API usable without external credentials
- `live`
  - Enabled when both OpenAI and Tavily keys are present
  - Uses real provider adapters
- `production`
  - Must have explicit CORS origins, provider keys, and `CONTENT_EVAL_DATABASE_URL`
  - Fails fast on invalid runtime configuration

## Cross-Cutting Concerns

- model clients
- external search adapters
- storage
- structured logging
- queued job execution
- export contracts

## Documentation Layout

- `docs/product/`
  - User problems, product goals, success criteria
- `docs/frontend/`
  - UI behaviors, review interactions, annotation patterns
- `docs/backend/`
  - Pipelines, ingestion, Python standards, orchestration, result synthesis
- `docs/agents/`
  - Agent responsibilities and evaluation workflow
- `docs/operations/`
  - Logging, traceability, health/readiness behavior, local/devops workflows
- `docs/process/`
  - Documentation hygiene, commit conventions, repo workflow
- `docs/plans/`
  - Active and completed execution plans

## Working Principle

The repository should expose enough structure that an agent can infer where to make a change without loading the entire knowledge base into context.
