# Architecture Map

This project is an agent-readable monorepo with a Next.js frontend and a FastAPI backend. The system is moving to an artifact-first design: the backend produces a complete analysis artifact, the UI renders that artifact plus a live event stream, and persistence is an optional adapter rather than the center of the model.

## Top-Level Domains

- `docs/`
  - System of record for product, architecture, process, and plans
- `apps/web/`
  - Next.js review workbench for intake, live progress, artifact rendering, review actions, and import/export
- `services/api/`
  - FastAPI API, artifact orchestration, agent registry, provider adapters, repositories, and backend tests
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
    - Top-level client coordinator for intake, live progress, artifact rendering, and review actions
  - `src/components/review/`
    - Presentational review components: hero, toolbar, progress area, document pane, comment rail, metrics, selection composer, connector overlay
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
    - OpenAI analysis adapter, Tavily similarity search adapter, Trafilatura extraction adapter, mock fallback adapters for local development
  - `repositories/`
    - Session-first in-memory artifact storage and optional PostgreSQL-backed artifact persistence
  - `services/`
    - Normalization, agent planning/scheduling, artifact assembly, review mutations, export building, worker loop

## Primary Architecture Decisions

- The API is the canonical producer of `AnalysisArtifact`.
- The UI renders artifact snapshots directly and does not depend on backend-only stitched view models.
- Live progress is a separate event stream, not the artifact itself.
- Session plus artifact export/import is the default local and open-source workflow.
- Workspace persistence remains optional for team or production deployments.
- Multi-agent execution is code-orchestrated:
  - one orchestrator
  - a registry of specialist agents
  - explicit dependencies
  - parallel execution for independent agents
  - dependent execution for synthesis/scoring steps

## Runtime Modes

- `session`
  - Default user-facing mode
  - No database required
  - Artifact and live events live in ephemeral backend/browser state
  - Export/import is the primary persistence mechanism
- `workspace`
  - Optional persisted mode
  - Stores artifact snapshots and review state in backend storage
  - Supports reopening prior runs
- `mock`
  - Default provider mode when live keys are absent
  - Uses deterministic local analysis/search/extraction providers
- `live`
  - Enabled when both OpenAI and Tavily keys are present
  - Uses real provider adapters

## Cross-Cutting Concerns

- artifact schema stability
- agent instructions and result schemas
- dependency-driven orchestration
- event streaming and debug traces
- optional persistence adapters
- export contracts

## Documentation Layout

- `docs/product/`
  - User problems, product goals, success criteria
- `docs/frontend/`
  - UI behaviors, progress timeline, review interactions, artifact import/export patterns
- `docs/backend/`
  - Pipelines, artifact contracts, Python standards, orchestration, result synthesis
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
