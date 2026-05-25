# Optional Reranker

Reranking is a second-stage retrieval step:

```text
initial recall -> rerank query/evidence pairs -> final top_k evidences
```

Embedding retrieval is optimized for recall. Reranker scoring is slower but can be more precise because it evaluates query-candidate pairs directly.

## Scores

- `vector_score`: first-stage vector/hybrid signal.
- `rerank_score`: second-stage reranker score.
- `final_score`: score used for final evidence ordering after reranking.

## Providers

- `noop`: preserves existing order and keeps reranking disabled.
- `local_rule_reranker`: deterministic lexical reranking for local development.
- `flagembedding`: optional lazy provider for BAAI-style reranker models.

Reranker remains disabled by default.
