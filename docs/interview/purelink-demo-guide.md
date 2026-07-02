# PureLink Interview Demo Guide

## 1. Demo Goal

Show PureLink as an engineering-focused RAG knowledge base system, not a one-off prompt demo. The demo should make these points visible:

- documents are processed through a structured ingestion pipeline
- retrieval modes can be inspected and compared
- citations are grounded in backend evidence
- retrieval traces and document status make failures diagnosable
- lightweight GraphRAG is source-grounded and maintainable
- processing jobs expose failures and retry without backend logs
- eval results are reproducible and honestly reported

## 2. Local Setup

For local test and lint commands:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Run core checks:

```bash
make test
cd frontend && npm run lint
cd frontend && npm run build
```

## 3. Docker Setup

```bash
cp .env.example .env
docker compose up -d --build db redis api worker frontend
docker compose ps
```

Open:

- Frontend: `http://localhost:3000`
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

Useful commands:

```bash
docker compose logs -f api worker frontend
docker compose restart api worker frontend
docker compose down
docker compose down -v
```

`docker compose down -v` deletes the database volume. Use it only when you want a clean local reset.

## 4. Recommended Demo Flow

### Step 1: Open KB Workspace

Create or open a personal KB. If you want to demonstrate team permissions, create a team KB and add a member through the invite flow.

Upload a small set of text documents. Good demo sources are:

- `README.md`
- `docs/rag/retrieval-layer.md`
- `docs/retrieval-and-citations.md`
- `docs/ingestion/file-processing-pipeline.md`
- `docs/ingestion/document-blocks.md`
- `docs/rag/lightweight-graphrag.md`
- `docs/product/kb-workspace.md`
- `docs/development/testing-and-smoke.md`

### Step 2: Upload and Inspect Documents

Open the Documents tab and wait for processing to finish. Show that the document row exposes status/debug instead of requiring backend logs.

### Step 3: Ask a Normal Factual Question

Use the Ask tab:

```text
What retrieval modes does PureLink support?
```

Show the answer and citations.

### Step 4: Ask a Technical API or Config Question

Use:

```text
Where is CHUNK_STRATEGY configured?
```

Explain that technical tokens are better suited to `hybrid_text` or `auto -> hybrid_text`.

### Step 5: Ask a Relation or Dependency Question

Use:

```text
How are DocumentBlock and chunks related?
```

Explain how relation/dependency queries can route toward `graph_vector_mix` through the rule-based router.

### Step 6: Show Retrieval Details and Trace

Open Retrieval Details or Retrieval Debug. Show:

- requested mode
- selected mode
- router reason for `auto`
- citations
- trace id
- retrieved evidence list

### Step 7: Show Document Processing Inspector

From the Documents tab, open document status. Highlight:

- processing status
- RAG-ready badge
- block, chunk, citation unit, vector index, and graph index counts
- warnings/errors
- copyable debug JSON

### Step 8: Show Processing Jobs

Open the Processing Jobs panel in the Documents tab. Highlight:

- running, failed, and completed job counts
- status filter and document search
- current step and attempt count
- error code/message for failed jobs
- retry behavior for owner/admin users

Frame retry honestly: it creates a new queued worker job. It does not run parsing
synchronously in the browser or API request.

### Step 9: Show Graph Explorer

Open the Graph tab. Demonstrate:

- entity search
- relation type filter
- selecting an entity to inspect one-hop relations
- opening relation sources
- jumping from a source document to Document Processing Inspector
- exporting JSON or CSV

Keep the framing honest: this is a lightweight source-grounded graph explorer, not a Neo4j-style graph canvas.

### Step 10: Show RAG Eval Baseline

Open [rag-eval-baseline-summary.md](rag-eval-baseline-summary.md), then run:

```bash
make eval-rag-baseline
```

Explain that the runner builds temporary KBs from repository docs and compares fixed chunking, block-aware chunking, hybrid text, graph-vector mix, and auto router.

## 5. Suggested Demo Questions

Overview:

```text
What is PureLink's retrieval layer responsible for?
Give me an overview of the KB workspace.
```

Technical/API/config:

```text
Where is CHUNK_STRATEGY configured?
What does hybrid_text retrieval do?
Which trace metadata is returned for auto mode?
```

Relation/dependency:

```text
How are DocumentBlock and chunks related?
How does GraphRAG relation provenance work?
What is the relationship between graph maintenance and team permissions?
```

Factual QA:

```text
What retrieval modes does PureLink support?
Is the reranker required?
What does the RAG eval baseline compare?
```

Citation/debug:

```text
Which sources support this answer?
What selected retrieval mode and trace id did this answer use?
```

Document processing:

```text
Is this document RAG-ready?
Which processing step failed?
Can this failed document be retried?
```

Graph explorer:

```text
Show entities related to DocumentBlock.
Which source snippets support this relation?
```

## 6. What to Say in Interviews

Short version:

```text
PureLink is a personal and team knowledge-base RAG system focused on engineering reliability. I built ingestion, block-aware chunking, multiple retrieval modes, query routing, citation grounding, retrieval traces, lightweight GraphRAG, eval baselines, and product-facing debugging tools such as the Document Inspector, Graph Explorer, and Processing Job Dashboard.
```

When showing Ask:

```text
The answer is not the only product. The evidence, citations, selected retrieval mode, and trace id are also part of the user-facing debugging loop.
```

When showing Graph Explorer:

```text
This is intentionally list-based and source-grounded. The goal is to inspect graph evidence and provenance, not to build a complex graph visualization system.
```

When showing eval:

```text
The eval is a small regression baseline over repository docs. It is useful because it is repeatable and exposes tradeoffs, not because it claims statistical significance.
```

## 7. Known Limitations

- The current GraphRAG is lightweight and rule-based.
- GraphRAG is lightweight, not Neo4j-scale.
- There is no external graph database.
- There is no graph canvas visualization.
- Auto router is rule-based, not LLM planning.
- Reranker is optional.
- Local hashed embedding is for deterministic tests, not production quality.
- The default local LLM provider can be heuristic for offline demos.
- The eval baseline is small and docs-based.
- `answer_contains_expected` is not calculated in the current baseline because the baseline evaluates retrieval and citation evidence, not generated answers.
- Production deployment still needs HTTPS, reverse proxy hardening, secret management, monitoring, and backup operations.
- OCR, ASR, and multimodal RAG are not part of the default Core path.

## 8. Troubleshooting

If smoke fails with Docker permissions:

```text
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Fix Docker access, then open a new shell and rerun `make smoke`.

If documents are not RAG-ready, open Document Processing Inspector and check:

- chunk count
- citation unit count
- vector index status
- latest processing job step
- error code/message

If retrieval quality looks wrong, check:

- retrieval mode
- selected mode when using `auto`
- trace id and trace metadata
- whether vector index metadata matches current embedding provider/model
- whether the expected source document was indexed
