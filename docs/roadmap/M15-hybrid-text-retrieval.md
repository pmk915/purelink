# PureLink M15 Upgrade Plan: Hybrid Text Retrieval

M15 adds a lightweight `hybrid_text` retrieval mode for technical knowledge bases.

## Goal

`hybrid_text` combines:

- vector candidates from the existing chunk retrieval path
- keyword candidates from a local tokenizer/scorer
- candidate merge and deduplication by chunk identity
- optional reranker reuse
- existing citation, context, trace, API, frontend debug, and eval flows

This is intended for queries involving API paths, config keys, file names, commands, error codes, migration ids, and other exact technical terms.

## Non-goals

- No Elasticsearch/OpenSearch.
- No external search service.
- No default mode switch.
- No LLM answer generation changes.
- No GraphRAG rewrite.
- No Query Router yet.

## Keyword Retrieval

The keyword retriever uses deterministic local tokenization. It preserves terms such as:

- `RERANKER_ENABLED`
- `/api/v1/knowledge-bases/{id}/rag-health`
- `app/services/retrieval/rerank_service.py`
- `20260525_0020`

Scoring is based on query-term overlap with small boosts for exact phrase, document-name, and technical-token matches.

## Hybrid Merge

Candidates are deduped by:

1. `chunk_db_id`
2. `document_id + chunk_id`
3. source locator plus text preview hash fallback

Merged candidates preserve:

- `vector_score`
- `keyword_score`
- `matched_terms`
- `candidate_sources`

When reranker is disabled, a simple combined score orders candidates. When reranker is enabled, merged candidates are passed to the existing reranker pipeline.

## Validation

Focused validation:

```bash
.venv/bin/python -m pytest tests/services/retrieval tests/eval
```

Full validation:

```bash
make test
make KEEP_STACK_UP=1 smoke
make smoke-docx-rag
cd frontend && npm run lint && npm run build && cd ..
git diff --check
```
