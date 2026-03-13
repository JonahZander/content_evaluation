# AGENTS.md

This repository is organized for coding agents first and humans second.
Use this file as a map, not as the full source of truth.

## Core Rules

1. Start with the user request and load only the docs needed for that task.
2. Treat `docs/` as the system of record for product, architecture, process, and plans.
3. Update relevant markdown files in the same change whenever behavior, architecture, or workflow changes.
4. Do not read unrelated docs by default. Frontend work should usually avoid backend docs unless the change crosses the boundary.
5. Prefer small, explicit plans and short-lived changes over large speculative rewrites.
6. Keep the codebase legible to future agents: predictable names, narrow files, explicit boundaries, and current docs.
7. If a recurring workflow appears, suggest a skill. If the information is project-specific architecture or product context, put it in `docs/` instead of a standalone skill.

## First Stop

- Project overview: `README.md`
- Repository map: `ARCHITECTURE.md`
- Documentation index: `docs/index.md`

## Progressive Disclosure

Read only the domain relevant to the task:

- Product goals and user flows:
  - `docs/product/index.md`
  - `docs/product/content-evaluation-platform.md`
- Frontend UX and review workbench:
  - `docs/frontend/index.md`
  - `docs/frontend/annotation-review-workbench.md`
- Backend pipeline and agent orchestration:
  - `docs/backend/index.md`
  - `docs/backend/analysis-pipeline.md`
- Agent responsibilities and evaluation workflow:
  - `docs/agents/index.md`
  - `docs/agents/multi-agent-workflow.md`
  - `docs/agents/how-to-add-an-agent.md` (when adding a new specialist agent)
- Logging, observability, and traceability:
  - `docs/operations/index.md`
  - `docs/operations/observability.md`
  - `docs/operations/local-development.md`
- Process, documentation hygiene, and commit conventions:
  - `docs/process/index.md`
  - `docs/process/documentation-maintenance.md`
  - `docs/process/commit-conventions.md`
  - `docs/process/known-issues.md` (known open issues and intentional simplifications)
- Active and completed execution plans:
  - `docs/plans/README.md`

## When To Read What

- For repository-wide changes:
  - Read `ARCHITECTURE.md`
  - Read the relevant domain index in `docs/`
- For frontend-only work:
  - Read `docs/frontend/index.md`
  - Read linked frontend docs as needed
  - Read backend docs only if the UI contract changes
- For backend-only work:
  - Read `docs/backend/index.md`
  - Read linked agent and operations docs as needed
  - Read frontend docs only if the user-facing workflow changes
- For agent workflow changes:
  - Read `docs/agents/index.md`
  - Read `docs/backend/analysis-pipeline.md`
  - Read `docs/operations/observability.md`
- For process or repo-maintenance changes:
  - Read `docs/process/index.md`
  - Read `docs/plans/README.md` if work spans multiple steps or sessions

## Documentation Freshness

Documentation must move with the code.

Update docs when you change:

- Product behavior or scope
- Agent responsibilities or model-routing rules
- Data contracts, ingestion paths, or storage layout
- UX flows, review interactions, or annotation behavior
- Logging, trace fields, or evaluation outputs
- Runtime mode rules, readiness checks, or local/Docker workflows
- Commit conventions, workflow rules, or repo structure

If user feedback changes how a feature should behave, update the relevant markdown in the same change set.

## Plans

Use `docs/plans/active/` for larger multi-step efforts that may span multiple sessions.
Move finished plans to `docs/plans/completed/`.
Keep plans concise and execution-oriented.

## Skills

Potential future skills should be proposed when work is repetitive, fragile, or tool-heavy.

Examples that may make sense later:

- Dataset import and normalization
- Search-evaluation tuning
- Annotation export and reviewer QA
- Release verification

Repo-local skills currently available:

- `.codex/skills/commit-style/SKILL.md`
- `.codex/skills/frontend-design/SKILL.md`

Do not create a skill for information that is really repository knowledge.
If the content explains this project's architecture, workflows, or domain language, prefer `docs/`.

## Commit Workflow

Use the repo-local commit guidance:

- Skill: `.codex/skills/commit-style/SKILL.md`
- Template: `.gitmessage.txt`
- Conventions: `docs/process/commit-conventions.md`

Keep commits focused. Include the relevant doc updates in the same commit whenever possible.
