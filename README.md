# PureLink

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-frontend-black.svg)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)

PureLink is an open-source knowledge workspace for teams. It turns documents and media files into searchable, citable knowledge that can be used for retrieval and question answering.

中文简述：PureLink 是一个团队知识工作台，可以上传文档、图片、音频和视频，经处理后进入检索、问答和来源引用链路。

## Highlights

- Personal and team knowledge bases with clear permission boundaries
- Team invitation, member management, and role-based document review
- Automatic document processing through `ProcessingJob`, Redis, and an independent worker service
- Unified `DocumentChunk` storage for text, PDF, image OCR, audio transcription, and video transcription
- `ready -> indexed` asynchronous indexing path with local fallback embedding
- Hybrid retrieval, lightweight rerank, Q&A, and structured citations
- Source preview pages with deep links for text ranges, PDF pages, image OCR regions, and audio/video time ranges
- Full Docker Compose stack including PostgreSQL, Redis, FastAPI API, worker, and Next.js frontend

## Supported Inputs

| Type | Formats | Processing path |
| --- | --- | --- |
| Text | `.txt`, `.md` | Extract text, chunk, index |
| Office / PDF | `.docx`, `.pdf` | Extract text; scanned PDFs fall back to OCR |
| Image | `.png`, `.jpg`, `.jpeg` | OCR, chunk, index |
| Audio | `.mp3`, `.wav`, `.m4a` | ASR transcription with timestamps |
| Video | `.mp4`, `.mov`, `.m4v` | Extract audio, ASR transcription with timestamps |

## Tech Stack

- Frontend: Next.js App Router, TypeScript, Tailwind CSS, TanStack Query
- API: FastAPI, Pydantic, SQLAlchemy 2.0
- Database: PostgreSQL 16
- Queue: Redis
- Worker: Python processing worker, plus legacy Go worker experiments
- Migrations: Alembic
- Retrieval: local embedding fallback, hybrid retrieval, lightweight rerank
- Tests: pytest, Bash E2E scripts, frontend lint/build checks
- Packaging: Docker Compose

## Architecture

```text
Browser
  -> Next.js frontend
  -> FastAPI API
  -> PostgreSQL metadata
  -> Redis processing queue
  -> Python worker
  -> local file storage
  -> DocumentChunk / index artifacts
  -> retrieve / ask / citation / preview
```

Processing flow:

```text
upload
  -> review if required
  -> ProcessingJob(document_process)
  -> extract / OCR / ASR
  -> DocumentChunk
  -> ready
  -> ProcessingJob(document_index)
  -> indexed
  -> retrieve / ask / citation
```

Team review rules:

- Personal uploads: process automatically.
- Team admin uploads: approved immediately, then process automatically.
- Team member uploads: wait for admin approval, then process.
- Rejected team documents do not enter retrieval.

## Quick Start

### Run the full stack with Docker

```bash
git clone <your-fork-or-repo-url>
cd purelink
cp .env.example .env
docker compose up -d --build
```

Open:

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health`

Stop the stack:

```bash
docker compose down
```

The Docker stack includes:

- `db`: PostgreSQL
- `redis`: processing queue
- `api`: FastAPI service
- `worker`: background document processing worker
- `frontend`: production Next.js frontend

### Run backend and frontend manually

Backend:

```bash
cd purelink
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Manual local mode still requires PostgreSQL and Redis to be available through `.env`.

## Configuration

Copy `.env.example` to `.env` before running the stack.

Important variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Backend database URL for non-Docker runs | local PostgreSQL |
| `REDIS_URL` | Redis queue URL for non-Docker runs | `redis://localhost:6379/0` |
| `APP_PORT` | Host port for API | `8000` |
| `FRONTEND_PORT` | Host port for frontend | `3000` |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-facing API URL baked into the frontend image | `http://localhost:8000/api/v1` |
| `EMBEDDING_PROVIDER` | Embedding provider | `local_hashed_bow` |
| `OCR_PROVIDER` | OCR provider | `tesseract` |
| `ASR_PROVIDER` | ASR provider | `vosk` |
| `LLM_PROVIDER` | Answer generator | `heuristic` |

Note: `NEXT_PUBLIC_API_BASE_URL` is a build-time variable in Next.js. If you change it for Docker, rebuild the frontend image:

```bash
docker compose up -d --build frontend
```

## Verification

Run Python tests:

```bash
pytest -q
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

Run smoke test:

```bash
make smoke
```

Run full E2E:

```bash
make e2e
```

Current scripted E2E coverage:

- Personal upload -> processing job -> retrieval -> ask -> conversation
- Team invite -> member upload -> admin review -> processing job -> retrieval -> ask
- Permission boundaries for team members and outsiders
- Worker processing and source preview chunk availability

## Project Structure

```text
purelink/
├── app/                    # FastAPI app, models, schemas, services, workers
├── alembic/                # Database migrations
├── frontend/               # Next.js frontend and frontend Dockerfile
├── scripts/e2e/            # Bash E2E scripts
├── tests/                  # pytest test suite
├── docs/                   # Design notes
├── worker-go/              # Legacy / experimental Go worker
├── data/                   # Local runtime artifacts, ignored in production use
├── docker-compose.yml      # Full local stack
├── Dockerfile              # API / worker image
├── Makefile                # Common developer commands
└── README.md
```

## Developer Commands

```bash
make up              # start full Docker stack
make down            # stop Docker stack
make logs            # follow service logs
make test-python     # run Python tests
make smoke           # run minimal Docker smoke flow
make e2e             # run all E2E scripts
```

## Documentation

- [PLAN.md](PLAN.md): roadmap and milestone plan
- [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md): implementation history
- [DEV_COMMANDS.md](DEV_COMMANDS.md): practical local commands
- [frontend/README.md](frontend/README.md): frontend-specific setup notes
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution workflow
- [LICENSE](LICENSE): MIT license

## Roadmap

- Object storage abstraction for MinIO / S3-compatible backends
- Stronger external embedding provider support
- More production-ready vector storage
- Richer citation preview with PDF/image region highlighting
- Optional audio/video playback seek from citations
- Better deployment profiles for cloud environments

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting larger changes.

Recommended contribution checklist:

- Keep the Docker stack runnable.
- Add or update tests for backend behavior.
- Run frontend lint/build when touching `frontend/`.
- Avoid breaking the `ready -> indexed -> retrieve / ask / citation` path.

## License

PureLink is released under the [MIT License](LICENSE).
