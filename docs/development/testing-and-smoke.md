# Testing and Smoke

## Unit and Integration Tests

```bash
make test
```

This runs Python tests and Go worker tests.

Focused examples:

```bash
.venv/bin/python -m pytest tests/services/retrieval tests/eval
.venv/bin/python -m pytest tests/services/document_parsing tests/services/indexing
.venv/bin/python -m pytest tests/services/knowledge_graph tests/test_graph_maintenance.py
.venv/bin/python -m pytest tests/test_document_status.py
```

## Smoke

Personal flow:

```bash
make KEEP_STACK_UP=1 smoke
docker compose stop
```

DOCX RAG smoke:

```bash
make up
make smoke-docx-rag
docker compose stop
```

## RAG Eval

```bash
make eval-rag
make eval-rag-baseline
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

Run `make eval-rag-baseline` after retrieval or graph lifecycle changes. It
rebuilds temporary eval KBs and verifies the fixed/block-aware and retrieval
mode baseline report still runs, including `graph_vector_mix`.

## Graph Lifecycle Checks

Graph lifecycle coverage should include:

- document deletion removes graph mentions and source-grounded relation evidence
- shared entities and relations from other documents are preserved
- orphan entities can be cleaned explicitly
- duplicate relation evidence can be deduplicated
- single-document graph rebuild uses existing chunks/citation units and does not rebuild the vector index
- personal owners and team admins can run maintenance
- team members can export/view graph data but cannot run maintenance

## Document Processing Inspector Checks

Document status coverage should include:

- indexed documents with chunks, citation units, and vector index return `rag_ready=true`
- missing chunks, citation units, or vector index return `rag_ready=false`
- missing graph index is reported as optional and does not block base RAG readiness
- failed processing status exposes error code/message and latest processing step
- personal KB owner can read status
- team members can read status
- unauthorized users and missing documents receive the existing 404-style access response

Frontend validation for the inspector is currently lint/build based. The project
does not include a dedicated browser component test setup, so M19 avoids adding a
new frontend test framework.

## Retrieval Debug Modes

The workspace Retrieval Debug tab can compare:

- `chunk_only`
- `overview`
- `graph_vector_mix`
- `hybrid_text`
- `auto`

Use `hybrid_text` when validating exact technical terms such as API paths, config keys, file paths, commands, error codes, or migration ids.
Use `auto` when validating the rule-based query router and confirm the response includes `requested_mode`, `selected_mode`, and `router_reason`.

## GitHub Actions

CI should validate tests and smoke against Docker Compose. When smoke fails, inspect:

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=120 db
```

## Deterministic Smoke Query

The personal smoke query is lexically aligned with `tests/fixtures/personal_sample.txt`. This is deliberate: smoke should validate upload, processing, retrieval, ask, and conversation flow without depending on subtle semantic embedding behavior.

If the primary query returns no results, smoke tries a second deterministic fallback query before failing. If both fail, the script prints:

- retrieve response body
- `kb_id` and `doc_id`
- document list
- document RAG debug response
- document status inspector response
- KB RAG health
- provider status

Use these diagnostics to identify whether the failure is in parsing, block
persistence, chunk persistence, citation unit creation, vector index metadata,
provider configuration, stale index filtering, graph index extraction, or
retrieval scoring.

Useful local checks:

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=120 db
```
