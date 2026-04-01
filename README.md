# Content Evaluation

Content Evaluation is an artifact-first editorial review tool for blog posts and long-form drafts. It turns a URL, pasted draft, uploaded text file, or saved artifact into one reviewable object with agent findings, evidence-backed comments, live progress, reviewer decisions, replies, and exports, so the product feels like a real editorial workflow instead of a pile of disconnected model calls.

The backend's primary job is to produce a complete `AnalysisArtifact`. The web app renders that artifact, streams live progress while it is being built, and lets reviewers add replies and decisions on top of it. The same API/services should be usable without the frontend when someone wants to run the analysis pipeline directly and export the result.

## Run The Demo

1. Start the API with `npm run dev:api`.
2. Start the web app with `npm run dev:web`.
3. Open the app and click `Open demo review`.

Recommended demo path:

- Scan the review summary and metrics.
- Open a few agent comments in the rail and inspect the linked evidence.
- Mark a couple of findings `accepted` or `rejected`, then add a reply.
- Export `Todo`, `Markdown`, or `JSON` from the toolbar.
- If you want to show the live pipeline instead, start a fresh run from pasted text, URL import, or file upload after the demo artifact walkthrough.

Current supported inputs:

- A blog post URL
- An uploaded `.txt` or `.md` file
- Pasted raw text
- Imported artifact JSON

Current analysis and review capabilities:

- Select which agents should run for a given analysis
- Fact-check key claims and surface overlapping public posts as linked research
- Estimate whether content is likely AI-generated
- Summarize the article with fact-check-backed TL;DR, audience, overlap, and overall review metrics
- Run editorial review plus post-run revised-markdown generation with dependency-aware orchestration
- Attach agent comments to anchored text spans
- Render a review summary panel plus claim-by-claim evidence links above and beside the source text
- Let a human reviewer reply to agent comments
- Let a human reviewer mark agent comments as `accepted`, `rejected`, or `uncertain`
- Let a human reviewer add standalone comments on new text selections
- Export the artifact as Todo Markdown, full Markdown, or JSON

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
