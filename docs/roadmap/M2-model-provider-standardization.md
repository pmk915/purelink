# PureLink M2 Upgrade Plan: Model Provider Standardization

## Goal

M2 standardizes PureLink model access behind provider interfaces without changing the current default embedding behavior or adding heavy required dependencies.

M2 follows M1 retrieval refactor:

- `app/services/retrieval/` is the unified retrieval layer.
- Ask flows call `retrieval_service.retrieve()`.
- `qa.py` no longer owns chunk retrieval on the main ask path.
- Legacy `retrieve_chunks_for_documents` remains only for compatibility/internal use.

## Scope

Add provider interfaces and factories for:

- `EmbeddingProvider`
- `RerankerProvider`
- `LLMProvider`

Preserve current runtime behavior where possible:

- Keep fastembed as the lightweight local embedding path.
- Do not switch the default embedding model.
- Do not enable a heavy reranker.
- Do not add GraphRAG, LangChain, LangGraph, agent runtime, or index version tables.
- Do not change frontend UI or response compatibility.

## Target Structure

```text
app/providers/
  embedding/
    base.py
    factory.py
    fastembed_provider.py
    legacy_adapter.py
  reranker/
    base.py
    factory.py
    noop_reranker.py
  llm/
    base.py
    factory.py
    legacy_adapter.py
```

## Acceptance Criteria

1. `app/providers/` package exists.
2. Embedding provider interface and factory exist.
3. Existing embedding behavior remains backward compatible.
4. Reranker provider interface and no-op provider exist.
5. Reranker config has safe defaults and does not require heavy models.
6. LLM provider interface exists, with legacy adapter prepared for future migration.
7. Provider status remains backward compatible and reports reranker status.
8. README and retrieval docs explain the provider layer.
9. Existing retrieval behavior and smoke tests continue to pass.

## Future Work

- M3: real reranker provider.
- M4: index versioning for embedding model mismatch detection.
- Later: OpenAI-compatible embedding/rerank APIs, graph-aware retrieval, and agent tools.
