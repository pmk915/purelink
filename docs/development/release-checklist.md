# Release Checklist

Use this checklist before creating a demo branch, milestone tag, or interview
recording. Do not create a tag until the repository state and checks are
confirmed.

## Git State

- `git status --untracked-files=all` is clean.
- `git log --oneline -12` shows the expected latest milestone commits.
- `git diff --check` reports no whitespace errors.

## Tests

Run:

```bash
make test
cd frontend && npm run lint
cd frontend && npm run build
make docs-check
```

Recommended before a public demo:

```bash
make smoke
```

Run eval only when retrieval logic, graph retrieval, eval cases, or docs used as
the eval corpus changed:

```bash
make eval-rag-baseline
```

## Docker

```bash
docker compose config
docker compose up -d --build db redis api worker frontend
docker compose ps
```

Verify:

- frontend is reachable at `http://localhost:3000`
- API health is reachable at `http://localhost:8000/api/v1/health`
- Swagger is reachable at `http://localhost:8000/docs`
- `docker compose logs -f api worker frontend` shows no repeated startup errors

Stop local services when finished:

```bash
docker compose down
```

Use `docker compose down -v` only for an intentional local data reset.

## Docs

- `README.md` is still a concise project entry point.
- `docs/README.md` links to current product, RAG, ingestion, development, and interview docs.
- `docs/interview/purelink-demo-guide.md` matches the current demo flow.
- `docs/interview/rag-eval-baseline-summary.md` contains only actual runner output.
- Known limitations are documented honestly.
- `make docs-check` passes.

## Data Hygiene

Do not commit:

- `.env`, `.env.production`, `.env.production.local`
- `data/`
- `logs/`
- `models/`
- SQLite or local DB files such as `*.sqlite`, `*.sqlite3`, `*.db`
- `node_modules/`
- `frontend/.next/`
- `__pycache__/`
- `.pytest_cache/`

Useful check:

```bash
find . \
  \( -path "./.git" -o -path "./node_modules" -o -path "./frontend/node_modules" -o -path "./data" -o -path "./logs" -o -path "./models" \) -prune \
  -o \( -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.db" -o -name ".env" -o -name ".env.production" -o -name ".env.production.local" -o -name "__pycache__" -o -name ".pytest_cache" -o -path "./frontend/.next" \) \
  -print
```

## Optional Release Tag

Commands only. Do not run automatically:

```bash
git tag -a v0.2.0-rag-productization -m "PureLink RAG productization milestone"
git push origin v0.2.0-rag-productization
```
