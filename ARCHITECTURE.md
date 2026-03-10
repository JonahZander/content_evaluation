# Architecture Map

This project is implemented as an agent-readable monorepo with a Next.js frontend and a FastAPI backend.

## Top-Level Domains

- `docs/`
  - System of record for product, architecture, process, and plans
- `apps/web/`
  - Next.js routes, review workbench UI, export actions
- `services/api/`
  - FastAPI API, provider adapters, repositories, orchestration services
- `.codex/skills/`
  - Repo-local skills for recurring agent workflows

## Layering

Frontend features should converge toward:

1. `types`
2. `lib`
3. `components`
4. `app`

Backend features should converge toward:

1. `domain`
2. `providers/interfaces`
3. `providers/*`
4. `repositories`
5. `services`
6. `api`

Cross-cutting concerns should stay explicit:

- model clients
- external search adapters
- storage
- telemetry
- feature flags

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
  - Logging, traceability, metrics, run inspection, local/devops workflows
- `docs/process/`
  - Documentation hygiene, commit conventions, repo workflow
- `docs/plans/`
  - Active and completed execution plans

## Working Principle

The repository should expose enough structure that an agent can infer where to make a change without loading the entire knowledge base into context.
