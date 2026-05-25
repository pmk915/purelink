# Retrieval Layer

The retrieval layer lives under `app/services/retrieval/`.

Its public entrypoint is:

```python
retrieval_service.retrieve(request: RetrievalRequest) -> RetrievalResult
```

## Core Types

- `RetrievalRequest`: query, KB id, user id, mode, top_k, permission context, DB/session internals.
- `RetrievalMode`: `chunk_only`, `overview`, `graph_vector_mix`, plus future placeholders.
- `RetrievedEvidence`: normalized citation-ready evidence with document/chunk/citation ids and scores.
- `RetrievalResult`: final evidence list, context text, reranker usage, trace id, and compatibility metadata.

## Modes

- `CHUNK_ONLY`: vector/hybrid chunk retrieval with citation unit selection.
- `OVERVIEW`: adapter around the existing overview retrieval flow.
- `GRAPH_VECTOR_MIX`: merges graph-derived candidates with vector candidates, then reuses final evidence selection and optional reranker.

Unsupported future modes fallback to `CHUNK_ONLY`.

## Why This Exists

QA generation should not own retrieval details. The QA service asks for evidence and context; the retrieval layer owns candidate retrieval, graph merge, reranking, trace, and citation-ready evidence construction.
