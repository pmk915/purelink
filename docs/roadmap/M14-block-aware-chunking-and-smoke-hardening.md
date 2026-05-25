# PureLink M14 Upgrade Plan: Block-aware Chunking and Smoke Retrieval Hardening

## Goals

M14 improves two production-adjacent areas:

- Use `DocumentBlock` structure during ingestion when `CHUNK_STRATEGY=block_aware`.
- Make personal smoke retrieval failures actionable instead of only reporting `results: []`.

The default chunk strategy remains `fixed`, so existing Core deployments keep the established flat-text behavior unless block-aware chunking is explicitly enabled.

## Smoke Hardening

Personal smoke now waits for RAG readiness before `/retrieve`:

- document processing status is `ready` or `indexed`
- chunk count is greater than zero
- citation unit count is greater than zero
- vector index status is `indexed`
- vector index compatibility is not false

If retrieval returns no results, the script prints:

- primary and fallback retrieve response bodies
- `kb_id` and `doc_id`
- document list
- document RAG debug response
- KB RAG health response
- provider status response

A fallback query is attempted to distinguish query/ranking issues from parsing, chunking, indexing, or filtering issues.

## Block-aware Chunking

`CHUNK_STRATEGY` supports:

- `fixed`: existing flat normalized text chunking
- `block_aware`: chunks are generated from persisted document blocks

The block-aware strategy:

- keeps heading context in `heading_path`
- groups text under the same section
- keeps small tables as standalone chunks
- splits large tables by rows/lines
- treats code blocks as standalone chunks
- falls back to boundary-based splitting for oversized sections
- falls back to fixed chunking if blocks are missing or invalid

Chunk metadata records:

- `chunk_strategy`
- `heading_path`
- `section_title`
- `block_types`
- `source_block_ids`
- `source_block_order_indexes`
- `source_locators`

## Non-goals

M14 does not add Agent workflow, new frontend pages, external parsers, OCR/VLM, or full LightRAG chunking parity.

## Validation

Required validation:

```bash
.venv/bin/python -m pytest tests/services/document_chunking tests/services/document_parsing tests/services/retrieval tests/eval
make test
make KEEP_STACK_UP=1 smoke
make smoke-docx-rag
cd frontend && npm run lint && npm run build && cd ..
git diff --check
```

Do not run `make down` automatically during this milestone. If local cleanup is needed, use `docker compose stop`.
