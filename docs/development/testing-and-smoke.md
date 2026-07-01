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
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

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
- KB RAG health
- provider status

Use these diagnostics to identify whether the failure is in parsing, block persistence, chunk persistence, citation unit creation, vector index metadata, provider configuration, stale index filtering, or retrieval scoring.

Useful local checks:

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=120 db
```
