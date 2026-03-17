# Local Development

## Goals

- Fast local iteration for the web app and API without forcing Docker for every code change
- Full-stack Docker support for repeatable deployment and local integration testing
- Durable workspace-mode analysis backed by Postgres, with session mode still available for lightweight local use

## Local Workflow

- Use `nvm use` at the repository root to activate the pinned Node version from `.nvmrc`
- Run the web app with `npm run dev:web`
- Run the API with `npm run dev:api`
- Use Postgres-backed `workspace` persistence as the default internal review flow
- Keep `session` mode available for lightweight local-only runs that do not need reload/restart durability
- Set `CONTENT_EVAL_DATABASE_URL` whenever you want durable workspace restore across browser reloads or backend restarts
- Omit provider keys in development to use mock providers
- Set `CONTENT_EVAL_TAVILY_API_KEY` plus the API key for the configured analysis provider family to enable live analysis
- Tavily currently powers live search and extraction flows
- OpenAI, Anthropic, and Gemini are currently analysis providers, not search providers
- Use the artifact import/export controls in the UI when you want to save or reload work without a database

## Common Commands

- Web tests: `npm run test:web`
- Web typecheck: `npm run typecheck:web`
- Browser E2E tests: `npm run test:e2e`
- Browser E2E headed: `npm run test:e2e:headed`
- Browser E2E UI mode: `npm run test:e2e:ui`
- API tests: `npm run test:api`
- API lint: `npm run lint:api`
- API typecheck: `npm run typecheck:api`

## Playwright Setup

- Playwright was installed in `apps/web` using the official setup command from the Playwright docs:
  - `npm init playwright@latest`
- The repo keeps the generated Playwright config in:
  - `apps/web/playwright.config.ts`
- The browser tests live in:
  - `apps/web/e2e/`
- The Playwright config starts both:
  - the FastAPI API in `CONTENT_EVAL_APP_ENV=test`
  - the Next.js app on `127.0.0.1:3000`

## Playwright Notes

- The E2E suite currently runs on Chromium.
- The browser flows cover:
  - pasted-text submission
  - agent selection and hydrated workbench startup
  - agent reply and review-state updates
  - standalone reviewer comments from browser text selection
  - Markdown and JSON export popups
  - invalid upload handling
- Playwright stores browser binaries outside the repo and writes local reports under `apps/web/` paths that are ignored by Git.

## Docker Workflow

- Use `docker-compose.yml` to start:
  - web
  - api
  - postgres
- The Compose project is explicitly named `content_evaluation_dev` so the stack is easy to distinguish from other local Docker projects.
- The `api` service loads its service-local environment from `services/api/.env`.
- Compose still overrides `CONTENT_EVAL_DATABASE_URL` for the `api` container so Postgres resolves to the Docker service host (`postgres`) instead of local `localhost`.
- The compose stack publishes:
  - web on `http://localhost:3000`
  - api on `http://localhost:8000`
  - postgres on `localhost:5432`

## Configuration

- Use `.env` files for both local and Docker-driven workflows
- Keep provider API keys and database URLs out of committed files
- The default UI path is `workspace + artifact`; `session` mode remains optional
- `CONTENT_EVAL_APP_ENV=production` requires:
  - explicit `CONTENT_EVAL_CORS_ORIGINS`
  - `CONTENT_EVAL_DATABASE_URL` for workspace persistence
  - `CONTENT_EVAL_TAVILY_API_KEY`
  - the API key for the configured analysis provider family
