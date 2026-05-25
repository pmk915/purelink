# PureLink M11: Smoke Fix, Repository Cleanup, and Docs Polishing

## Goal

M11 stabilizes the repository after RAG v2 and Lightweight GraphRAG work.

It focuses on:

- deterministic personal smoke retrieval
- cleaner tracked files
- better documentation structure

M11 does not add new backend RAG features.

## Smoke Fix

The personal E2E fixture and query are now lexically aligned so CI smoke does not depend on subtle semantic retrieval behavior.

The script also prints the retrieve response, KB/document ids, and document list if retrieval returns no results.

## Repository Cleanup

M11 removes accidental/generated tracked artifacts:

- root `=0.0.9,`
- `data/smoke/`

It also moves:

- `test.md` -> `docs/development/frontend-backend-integration-test.md`
- `DEV_COMMANDS.md` -> `docs/development/dev-commands.md`

Runtime `data/` is ignored while preserving `data/.gitkeep`.

## Documentation Structure

M11 adds `docs/README.md` as the documentation index and creates focused docs for:

- RAG pipeline
- retrieval layer
- model providers
- optional reranker
- index metadata
- retrieval trace
- RAG evaluation
- file processing
- document blocks
- lightweight GraphRAG
- Docker deployment
- testing and smoke

## Validation

Expected validation:

```bash
make KEEP_STACK_UP=1 smoke
make smoke-docx-rag
make test
git diff --check
```
