# Documentation Index

Use this directory as the repository knowledge base.

Load only the section needed for the current task.

## Sections

- `product/`
  - Product goals, user journeys, analysis outputs
- `frontend/`
  - Review UI, annotations, connector behavior, reviewer actions
- `backend/`
  - Ingestion, artifact orchestration, background processing, exports, Python standards
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
- Code walkthrough and review order:
  - `docs/process/codebase-walkthrough.md`
- LLM backend setup and prompt locations:
  - `docs/process/llm-backend-walkthrough.md`
- Artifact data model reference:
  - `docs/backend/data-contracts.md`
- Adding a new agent:
  - `docs/agents/how-to-add-an-agent.md`
- Known open issues and intentional simplifications:
  - `docs/process/known-issues.md`
- Goals, feature ideas, and improvement areas:
  - `docs/roadmap.md`

## Current Product Surface

- Inputs: URL, pasted text, `.txt`, `.md`, imported artifact JSON
- Primary contract: `AnalysisArtifact` produced by the API and rendered by the UI
- Runtime modes: `session` by default, optional `workspace` persistence
- Review UI: paragraph-row text and comment layout, review summary panel, nearby claim-evidence chips, SVG connector lines, live agent progress, agent selection, artifact import/export
- Review actions: reply to comments, create reviewer comments, accept/reject/uncertain agent comments
- Agents: fact-check, AI-likelihood, value, audience, editorial, and synthesis; overlap research now hangs off fact-check instead of a standalone top-level similarity surface
- Exports: Markdown and JSON derived directly from the artifact
- Runtime visibility: `/health`, `/ready`, run events, SSE stream, optional debug trace
- Browser E2E coverage: Playwright installed through the official setup flow in `apps/web`
