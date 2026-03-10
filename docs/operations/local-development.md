# Local Development

## Goals

- Fast local iteration for the web app and API without forcing Docker for every code change
- Full-stack Docker support for repeatable deployment and local integration testing

## Local Workflow

- Use `nvm use` at the repository root to activate the pinned Node version from `.nvmrc`
- Run the web app with `npm run dev:web`
- Run the API with `npm run dev:api`
- Point the API at Postgres via environment variables

## Docker Workflow

- Use `docker-compose.yml` to start:
  - web
  - api
  - postgres

## Configuration

- Use `.env` files for both local and Docker-driven workflows
- Keep provider API keys and database URLs out of committed files
