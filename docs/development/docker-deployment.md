# Docker Deployment

This guide documents PureLink's Docker deployment path for local demos and production-like Compose runs. It does not introduce Kubernetes, Helm, Terraform, or external managed services.

## 1. Local Docker Quick Start

```bash
cp .env.example .env
docker compose up -d --build db redis api worker frontend
docker compose ps
```

Open:

- Frontend: `http://localhost:3000`
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

Equivalent Makefile commands:

```bash
make docker-up
make docker-ps
make docker-logs
make docker-down
```

`docker compose down` stops and removes containers but keeps named volumes. `docker compose down -v` also deletes volumes, including the PostgreSQL database volume.

## 2. Production-like Compose

PureLink includes `docker-compose.prod.yml` as a production-like override for the existing local Compose file. It keeps the same service layout but sets production-oriented defaults, avoids exposing Postgres/Redis ports, and uses named volumes for app data, logs, and model cache.

Prepare the env file:

```bash
cp .env.production.example .env.production
```

Edit `.env.production` before starting:

- replace `AUTH_SECRET_KEY`
- replace `POSTGRES_PASSWORD`
- set public `API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `FRONTEND_BASE_URL`
- set CORS origins for the frontend domain

Start:

```bash
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build db redis api worker frontend
```

Or:

```bash
make docker-prod-up
```

Stop:

```bash
make docker-prod-down
```

The production-like compose file is a template for a single-host deployment. Put HTTPS, domain routing, request buffering, and public network policy behind a reverse proxy you control.

## 3. Environment Variables

Use `.env.example` for local demos and `.env.production.example` as a production-like template.

Key groups:

- App: `APP_ENV`, `APP_DEBUG`, `LOG_LEVEL`
- Auth: `AUTH_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`
- Database: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`
- Redis: `REDIS_URL`
- Frontend/API URLs: `API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, `FRONTEND_BASE_URL`, `CORS_ALLOW_ORIGINS`
- Storage: `DATA_DIR`, `UPLOAD_DIR`, `PARSED_DIR`, `CHUNKS_DIR`, `VECTOR_STORE_DIR`
- Models: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_MODEL_CACHE_DIR`
- LLM: `LLM_PROVIDER`, `LLM_API_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- Upload limits: `MAX_UPLOAD_SIZE_MB`, `ALLOWED_UPLOAD_EXTENSIONS`, `ALLOWED_UPLOAD_MIME_TYPES`
- Processing limits: `MAX_ACTIVE_JOBS_PER_USER`, `MAX_ACTIVE_JOBS_PER_KB`

Do not commit `.env`, `.env.production`, API keys, database dumps, upload data, vector indexes, logs, or model caches.

Default upload policy:

```env
MAX_UPLOAD_SIZE_MB=25
ALLOWED_UPLOAD_EXTENSIONS=.pdf,.docx,.md,.txt
ALLOWED_UPLOAD_MIME_TYPES=application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown,text/plain
```

The API enforces this policy on personal and team KB upload endpoints. The
frontend reads `GET /api/v1/upload/constraints` and performs a precheck before
sending files, but the backend remains the source of truth.

## 4. Service Layout

| Service | Purpose | Port | Healthcheck |
|---|---|---:|---|
| `db` | PostgreSQL metadata and app state | `5432` local only | `pg_isready` |
| `redis` | Processing queue | `6379` local only | `redis-cli ping` |
| `api` | FastAPI app, auth, KB APIs, QA, retrieval, graph endpoints | `8000` | `GET /api/v1/health` via Python urllib |
| `worker` | Async document parsing, chunking, vector indexing, graph indexing | none | No fake healthcheck; verify by logs and smoke |
| `frontend` | Next.js UI | `3000` | `GET /` via `wget` |

The API and worker reuse the same backend Docker image. The API runs Alembic migrations before starting Uvicorn:

```text
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Python and Go Worker Positioning

The supported Docker Compose processing path uses the Python `worker` service:

```text
python -m app.workers.processing_worker_main
```

This worker consumes the Redis processing queue and runs the current parser registry, `DocumentBlock` persistence, fixed or block-aware chunking, citation-unit generation, vector indexing, and lightweight graph indexing.

The repository also retains [`worker-go`](../../worker-go/) as an experimental/early implementation. It is not started by `docker-compose.yml` or `docker-compose.prod.yml`, is not the default supported deployment worker, and should not be assumed to have feature parity with the Python processing path. Go tests remain in CI to keep that experimental implementation buildable and maintainable; passing those tests does not establish behavioral equivalence between both workers.

## 5. Data Directories and Volumes

Local compose mounts host directories into API and worker containers:

- `./data:/app/data`
- `./logs:/app/logs`
- `./models:/app/models`

Important subdirectories:

- `data/uploads`: uploaded source files
- `data/parsed`: parsed text artifacts
- `data/chunks`: chunk artifacts
- `data/vector_store`: local vector indexes
- `logs`: app and worker logs
- `models`: embedding/reranker/model cache

Production-like compose uses named volumes:

- `purelink_data:/app/data`
- `purelink_logs:/app/logs`
- `purelink_models:/app/models`
- `postgres_data:/var/lib/postgresql/data`

Back up the database and `data/vector_store` together where possible. If the database says a document is indexed but vector store files are missing, retrieval can become inconsistent.

## 6. Common Commands

Local:

```bash
make docker-up
make docker-ps
make docker-logs
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose restart api worker frontend
make docker-down
```

Production-like:

```bash
make docker-prod-up
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker frontend
make docker-prod-down
```

Validate config:

```bash
docker compose config
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml config
```

## 7. Smoke Verification

```bash
make smoke
```

The personal smoke flow validates:

- user registration and login
- personal KB creation
- unsupported and empty upload rejection
- document upload
- processing submission
- retrieval
- ask with citations
- conversation list/detail persistence

If smoke fails, inspect:

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=120 db
```

If Docker reports permission denied for `/var/run/docker.sock`, fix local Docker access and open a new shell. The application containers may be fine; the host user simply cannot talk to Docker.

## 8. Backup and Restore

Create a backup directory:

```bash
mkdir -p backups
```

Database backup:

```bash
docker compose exec db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backups/purelink.sql
```

Timestamped variant:

```bash
docker compose exec db sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "backups/purelink-$(date +%Y%m%d-%H%M%S).sql"
```

Database restore:

```bash
cat backups/purelink.sql | docker compose exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Data directory backup for local compose:

```bash
tar -czf "backups/purelink-data-$(date +%Y%m%d-%H%M%S).tar.gz" data logs models
```

Restore local data directories:

```bash
tar -xzf backups/purelink-data-YYYYMMDD-HHMMSS.tar.gz
```

For production-like named volumes, copy data out through a temporary container or use your host's Docker volume backup process. Keep database backups and app data backups aligned to avoid document/index mismatches.

## 9. Troubleshooting

API unhealthy:

- check `docker compose logs --tail=200 api`
- confirm `DATABASE_URL` points to `db:5432`
- confirm Alembic migrations are not failing
- confirm `AUTH_SECRET_KEY` is set

Worker not processing:

- check `docker compose logs --tail=200 worker`
- confirm Redis is healthy
- confirm `PROCESSING_QUEUE_KEY` matches API and worker
- run `make smoke` or upload a small text file and inspect document status

Frontend cannot reach API:

- confirm `NEXT_PUBLIC_API_BASE_URL` was set before frontend image build
- rebuild frontend after changing API URLs
- check browser console for CORS failures
- confirm CORS origins match the frontend URL

Retrieval works poorly after changing embedding model:

- reindex documents after changing `EMBEDDING_PROVIDER` or `EMBEDDING_MODEL`
- check document status and vector index metadata
- back up `data/vector_store` with the database

Docker build includes unexpected local data:

- check `.dockerignore`
- verify `data/`, `logs/`, `models/`, `.env`, `.env.*`, `.pytest_cache/`, and `__pycache__/` are excluded

## 10. Security Checklist

- Change `AUTH_SECRET_KEY`.
- Change `POSTGRES_PASSWORD`.
- Do not expose Postgres or Redis publicly in production.
- Do not commit `.env`, `.env.production`, database dumps, uploaded files, model caches, vector indexes, or logs.
- Back up the database and data directories together.
- Use HTTPS behind a reverse proxy for public deployment.
- Review upload size and file type policy before public exposure.
- Keep `APP_DEBUG=false` in production-like deployments.
- Restrict CORS origins to the real frontend domain.
