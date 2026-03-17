# Content Evaluation

Agent-first monorepo for an artifact-first editorial review tool that evaluates blog posts and long-form text.

The backend's primary job is to produce a complete `AnalysisArtifact`. The web app renders that artifact, streams live progress while it is being built, and lets reviewers add replies and decisions on top of it. The same API/services should be usable without the frontend when someone wants to run the analysis pipeline directly and export the result.

Current supported inputs:

- A blog post URL
- An uploaded `.txt` or `.md` file
- Pasted raw text
- Imported artifact JSON

Current analysis and review capabilities:

- Select which agents should run for a given analysis
- Fact-check key claims and surface overlapping public posts as linked research
- Estimate whether content is likely AI-generated
- Identify the post's main value and likely audience
- Run editorial and synthesis/scoring steps with dependency-aware orchestration
- Attach agent comments to anchored text spans
- Render a review summary panel plus claim-by-claim evidence links above and beside the source text
- Let a human reviewer reply to agent comments
- Let a human reviewer mark agent comments as `accepted`, `rejected`, or `uncertain`
- Let a human reviewer add standalone comments on new text selections
- Export the full artifact as Markdown or JSON

## Repository Layout

- `apps/web`
  - Next.js review workbench UI with a left text pane, right comment rail, connector lines, live progress, agent selectors, imports/exports, and review actions
- `services/api`
  - FastAPI backend in Python 3.12 with artifact generation, provider interfaces, agent registry/orchestration, optional persistence adapters, and SSE event streaming
- `docs`
  - System of record for product, architecture, process, and plans

## Local Commands

- Node version: `nvm use`
- Web: `npm run dev:web`
- API: `npm run dev:api`
- Web tests: `npm run test:web`
- Web typecheck: `npm run typecheck:web`
- Browser E2E tests: `npm run test:e2e`
- Browser E2E headed: `npm run test:e2e:headed`
- API tests: `npm run test:api`
- API typecheck: `npm run typecheck:api`
- API lint: `npm run lint:api`

Start here:

- Repo map: `ARCHITECTURE.md`
- Agent entrypoint: `AGENTS.md`
- Documentation index: `docs/index.md`
