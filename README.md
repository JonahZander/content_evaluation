# Content Evaluation

Agent-first monorepo for a review tool that evaluates blog posts and long-form text.

The product accepts:

- A blog post URL
- An uploaded text file
- Pasted raw text

The system runs a multi-agent analysis pipeline that can:

- Search for similar existing posts and possible topical overlap
- Estimate whether content is likely AI-generated
- Identify the post's main value and likely audience
- Score whether the content is worth reading
- Suggest targeted improvements and attach comments to text spans
- Export the full review as Markdown or JSON

## Repository Layout

- `apps/web`
  - Next.js review workbench UI
- `services/api`
  - FastAPI backend in Python 3.12+
- `docs`
  - System of record for product, architecture, process, and plans

## Local Commands

- Web: `npm run dev:web`
- API: `npm run dev:api`
- Web tests: `npm run test:web`
- API tests: `npm run test:api`

Start here:

- Repo map: `ARCHITECTURE.md`
- Agent entrypoint: `AGENTS.md`
- Documentation index: `docs/index.md`
