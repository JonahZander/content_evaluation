# Contributor verification

Preserve unrelated work and keep documentation aligned with behavior. Before proposing a release, run:

```sh
npm ci
uv sync --directory services/api --extra dev --frozen
npm run test:web
npm run typecheck:web
npm run build:web
npm run lint:api
npm run typecheck:api
npm run test:api
npm run test:e2e
docker build -f apps/web/Dockerfile .
docker build -f services/api/Dockerfile .
docker compose config
```

Run `npm audit --audit-level=moderate` and audit the locked Python production dependencies before release. Never commit `.env` files or real article content that is private or sensitive.
