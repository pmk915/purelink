# Docker Deployment

## Local Start

```bash
cp .env.example .env
make up
```

The stack includes:

- PostgreSQL
- Redis
- FastAPI API
- worker
- Next.js frontend

## Smoke Checks

```bash
make smoke
make smoke-docx-rag
```

Stop the stack:

```bash
make down
```

## Common Diagnostics

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=120 db
```

If frontend build fails around `/app/public`, ensure `frontend/public/.gitkeep` exists.

If personal smoke retrieval fails, inspect `scripts/e2e/01_personal_flow.sh` and `tests/fixtures/personal_sample.txt`; the query is intentionally lexically aligned with the fixture because CI defaults to deterministic local retrieval.
