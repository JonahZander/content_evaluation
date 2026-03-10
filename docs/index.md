# Documentation Index

Use this directory as the repository knowledge base.

Load only the section needed for the current task.

## Sections

- `product/`
  - Product goals, user journeys, analysis outputs
- `frontend/`
  - Review UI, annotations, connector behavior, reviewer actions
- `backend/`
  - Ingestion, orchestration, queued execution, exports, Python standards
- `agents/`
  - Agent roles, structured findings, evaluation workflow
- `operations/`
  - Logs, readiness, model usage visibility, local and Docker workflows
- `process/`
  - Documentation hygiene, commit rules, repo workflow
- `plans/`
  - Active and completed execution plans

## Reading Guide

- Product or scope questions:
  - `docs/product/index.md`
- UI or interaction questions:
  - `docs/frontend/index.md`
- Pipeline or service questions:
  - `docs/backend/index.md`
- Multi-agent behavior questions:
  - `docs/agents/index.md`
- Logging or run-inspection questions:
  - `docs/operations/index.md`
- Workflow or repo rules:
  - `docs/process/index.md`

## Current Product Surface

- Inputs: URL, pasted text, `.txt`, `.md`
- Review UI: left text pane, right comment rail, SVG connector lines
- Review actions: reply to comments, create reviewer comments, accept/reject/uncertain agent comments
- Exports: Markdown and JSON
- Runtime visibility: `/health`, `/ready`, run events, SSE stream
