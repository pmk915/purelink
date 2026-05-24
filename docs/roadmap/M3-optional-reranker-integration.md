# PureLink M3 Upgrade Plan: Optional Reranker Integration

## Goal

M3 connects the reranker provider layer to the retrieval pipeline while keeping reranking disabled by default.

After M3, retrieval supports:

```text
initial recall -> optional rerank -> final evidence selection
```

Default Core deployment remains lightweight:

- `RERANKER_ENABLED=false`
- `RERANKER_PROVIDER=noop`
- no heavy reranker dependency in the default Docker image

## Scope

- Formalize a lightweight `local_rule_reranker` provider.
- Add optional `flagembedding` provider with lazy import.
- Expand initial recall when reranker is enabled.
- Rerank final evidence candidates and populate `rerank_score`.
- Preserve citation behavior and existing ask/retrieve API compatibility.

## Non-Goals

- Do not require `BAAI/bge-reranker-v2-m3`.
- Do not add heavy dependencies to default requirements.
- Do not change embedding defaults.
- Do not add GraphRAG, retrieval trace tables, or index version tables.
- Do not rewrite QA generation.

## Acceptance Criteria

1. Reranker provider is integrated into `retrieval_service.retrieve()`.
2. Disabled/no-op behavior preserves current ordering.
3. `local_rule_reranker` works as an optional deterministic provider.
4. `flagembedding` exists as an optional lazy-import provider.
5. Enabled reranking expands initial candidate recall.
6. Final evidence list is reranked and trimmed to `top_k`.
7. `RetrievedEvidence.rerank_score` and `RetrievalResult.used_reranker` are set correctly.
8. Provider status reports disabled, local, and missing optional dependency states.
9. README and retrieval docs explain optional reranking.
10. Tests and DOCX RAG smoke pass.
