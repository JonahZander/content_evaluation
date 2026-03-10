# Content Evaluation

Agent-first monorepo for a split-pane editorial review tool that evaluates blog posts and long-form text.

Current supported inputs:

- A blog post URL
- An uploaded text file
- Pasted raw text

Current analysis and review capabilities:

- Search for similar existing posts and possible topical overlap
- Estimate whether content is likely AI-generated
- Identify the post's main value and likely audience
- Score whether the content is worth reading
- Attach agent comments to anchored text spans
- Let a human reviewer reply to agent comments
- Let a human reviewer mark agent comments as `accepted`, `rejected`, or `uncertain`
- Let a human reviewer add standalone comments on new text selections
- Export the full review as Markdown or JSON

## Repository Layout

- `apps/web`
  - Next.js review workbench UI with a left text pane, right comment rail, connector lines, exports, and review actions
- `services/api`
  - FastAPI backend in Python 3.12 with provider interfaces, repositories, queued run processing, and SSE event streaming
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
