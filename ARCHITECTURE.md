# Architecture Map

This project will be implemented as an agent-readable Next.js monorepo-style application structure, even if it starts as a single app.

## Top-Level Domains

- `docs/`
  - System of record for product, architecture, process, and plans
- `app/` or `src/app/`
  - Future Next.js routes and UI shells
- `src/features/ingestion/`
  - URL fetch, file upload, pasted-text intake, normalization
- `src/features/analysis/`
  - Multi-agent orchestration, prompts, model routing, result aggregation
- `src/features/review/`
  - Annotation UI, inline comments, suggestions, reviewer actions
- `src/features/evaluation/`
  - Final scoring, reading-worthiness assessment, summary synthesis
- `src/features/observability/`
  - Logs, traces, run metadata, model usage, audit surfaces
- `.codex/skills/`
  - Repo-local skills for recurring agent workflows

## Planned Layering

Each feature should converge toward the same internal shape:

1. `types`
2. `schemas`
3. `services`
4. `runtime`
5. `ui`

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
  - Pipelines, ingestion, orchestration, result synthesis
- `docs/agents/`
  - Agent responsibilities and evaluation workflow
- `docs/operations/`
  - Logging, traceability, metrics, run inspection
- `docs/process/`
  - Documentation hygiene, commit conventions, repo workflow
- `docs/plans/`
  - Active and completed execution plans

## Working Principle

The repository should expose enough structure that an agent can infer where to make a change without loading the entire knowledge base into context.
