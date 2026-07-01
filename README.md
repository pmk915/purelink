# PureLink

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-frontend-black.svg)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)

PureLink is an engineering-focused RAG knowledge base system for personal and team workspaces. It emphasizes document-structure-aware ingestion, hybrid retrieval, lightweight GraphRAG, citation grounding, retrieval traceability, RAG evaluation, and productized debugging tools.

It is not a production SaaS template, a full LightRAG clone, a graph database product, or a multimodal assistant. The current core focuses on text knowledge bases with clear local deployment and evaluation paths.

## What PureLink Solves

Typical RAG demos often hide the hard parts: document structure gets flattened, retrieval modes are hard to compare, citations are unstable, failures require reading backend logs, and there is no repeatable eval baseline.

PureLink turns those concerns into visible engineering surfaces:

- Personal and team knowledge base workspaces.
- Document ingestion with parser routing, document blocks, chunks, citation units, vector index metadata, and graph index metadata.
- Retrieval modes for `chunk_only`, `overview`, `graph_vector_mix`, `hybrid_text`, and `auto`.
- Citation-grounded Q&A and retrieval details.
- Retrieval trace metadata for debugging recall, reranking, router decisions, and final evidence.
- Document Processing Inspector for RAG readiness checks.
- Graph Explorer for entity search, relation filters, one-hop neighborhoods, and source provenance.
- A reproducible RAG eval baseline over repository docs.

## Architecture Overview

```text
Next.js frontend
  -> FastAPI API
  -> PostgreSQL business data
  -> Redis processing queue
  -> worker document parsing/chunking/indexing
  -> local vector store
```

Core backend areas:

- `app/api/v1/`: auth, personal KB, team KB, documents, QA, graph, and status endpoints.
- `app/services/document_parsing/`: parser registry and `DocumentBlock` creation.
- `app/services/document_chunking/`: fixed and block-aware chunking.
- `app/services/retrieval/`: retrieval modes, query router, trace, context, and citations.
- `app/services/knowledge_graph/`: lightweight GraphRAG extraction, lifecycle cleanup, retrieval, and export.
- `scripts/eval/`: retrieval/citation eval runners.

Core frontend areas:

- `frontend/components/knowledge-bases/knowledge-base-workspace.tsx`
- `frontend/components/qa/`
- `frontend/components/retrieval/`
- `frontend/components/documents/document-status-dialog.tsx`
- `frontend/components/graph/graph-explorer.tsx`

## Quick Start

Prerequisites:

- Python 3.12
- Node.js 24
- Docker Engine or Docker Desktop with Docker Compose v2

Install Python dependencies if you are running tests locally:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

## Docker Quick Start

```bash
cp .env.example .env
docker compose up -d --build db redis api worker frontend
docker compose ps
```

Open:

- Frontend: `http://localhost:3000`
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

Useful Docker commands:

```bash
docker compose logs -f api worker frontend
docker compose restart api worker frontend
docker compose down
docker compose down -v
```

`docker compose down -v` deletes the database volume. Use it only when you intentionally want to reset local data.

For production-like Compose, backup/restore commands, and troubleshooting, see [Docker Deployment](docs/development/docker-deployment.md).

## Smoke Test

```bash
make smoke
```

The smoke test starts the Docker stack, registers a user, creates a personal KB, uploads a document, runs retrieval, asks a question, and checks conversation persistence.

If Docker reports a socket permission error, run Docker Desktop or add your user to the Docker group, then open a new shell. The command needs access to `/var/run/docker.sock`.

## RAG Eval Baseline

```bash
make eval-rag-baseline
```

This builds temporary eval KBs from repository docs and compares:

- `fixed + chunk_only`
- `block_aware + chunk_only`
- `block_aware + hybrid_text`
- `block_aware + graph_vector_mix`
- `block_aware + auto`

Current results are recorded in [docs/interview/rag-eval-baseline-summary.md](docs/interview/rag-eval-baseline-summary.md). The numbers are a regression baseline, not a statistical benchmark.

## Test Commands

```bash
make test
cd frontend && npm run lint
cd frontend && npm run build
make smoke
make eval-rag-baseline
```

For a demo-readiness checklist, see [docs/development/testing-and-smoke.md](docs/development/testing-and-smoke.md).

## Interview Demo

Start here:

- [PureLink Interview Demo Guide](docs/interview/purelink-demo-guide.md)
- [PureLink Project Storyline](docs/interview/project-storyline.md)
- [Feature Map](docs/interview/feature-map.md)
- [RAG Eval Talking Points](docs/interview/eval-talking-points.md)

Recommended demo surfaces:

1. KB Workspace tabs: Ask, Documents, Graph, Retrieval Debug, Health, Settings.
2. Ask normal factual, technical/API/config, relation/dependency, and overview questions.
3. Show Retrieval Details, selected retrieval mode, trace id, and citations.
4. Open Document Processing Inspector from a document row.
5. Open Graph Explorer, filter relations, inspect source snippets, and jump to document status.
6. Show the eval baseline report and explain the honest findings.

## Key Docs Index

The full documentation index is [docs/README.md](docs/README.md).

High-value entries:

- [KB Workspace](docs/product/kb-workspace.md)
- [RAG v2 Architecture](docs/architecture/rag-v2-architecture.md)
- [Retrieval Layer](docs/rag/retrieval-layer.md)
- [Retrieval and Citations](docs/retrieval-and-citations.md)
- [Document Blocks](docs/ingestion/document-blocks.md)
- [File Processing Pipeline](docs/ingestion/file-processing-pipeline.md)
- [Lightweight GraphRAG](docs/rag/lightweight-graphrag.md)
- [RAG Evaluation](docs/rag/rag-evaluation.md)
- [Testing and Smoke](docs/development/testing-and-smoke.md)

## License

[MIT](LICENSE)
