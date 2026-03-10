# Local Development

## Goals

- Fast local iteration for the web app and API without forcing Docker for every code change
- Full-stack Docker support for repeatable deployment and local integration testing

## Local Workflow

- Use `nvm use` at the repository root to activate the pinned Node version from `.nvmrc`
- Run the web app with `npm run dev:web`
- Run the API with `npm run dev:api`
- Point the API at Postgres via `CONTENT_EVAL_DATABASE_URL` when persistent storage is needed
- Omit provider keys in development to use mock providers
- Set both `CONTENT_EVAL_OPENAI_API_KEY` and `CONTENT_EVAL_TAVILY_API_KEY` to enable live analysis

## Common Commands

- Web tests: `npm run test:web`
- Web typecheck: `npm run typecheck:web`
- API tests: `npm run test:api`
- API lint: `npm run lint:api`
- API typecheck: `npm run typecheck:api`

## Docker Workflow

- Use `docker-compose.yml` to start:
  - web
  - api
  - postgres
- The compose stack publishes:
  - web on `http://localhost:3000`
  - api on `http://localhost:8000`
  - postgres on `localhost:5432`

## Configuration

- Use `.env` files for both local and Docker-driven workflows
- Keep provider API keys and database URLs out of committed files
- `CONTENT_EVAL_APP_ENV=production` requires:
  - explicit `CONTENT_EVAL_CORS_ORIGINS`
  - `CONTENT_EVAL_DATABASE_URL`
  - OpenAI and Tavily keys
