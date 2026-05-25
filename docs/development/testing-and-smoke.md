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
docker compose down
```

DOCX RAG smoke:

```bash
make up
make smoke-docx-rag
make down
```

## RAG Eval

```bash
make eval-rag
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

## GitHub Actions

CI should validate tests and smoke against Docker Compose. When smoke fails, inspect:

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=120 db
```

## Deterministic Smoke Query

The personal smoke query is lexically aligned with `tests/fixtures/personal_sample.txt`. This is deliberate: smoke should validate upload, processing, retrieval, ask, and conversation flow without depending on subtle semantic embedding behavior.
