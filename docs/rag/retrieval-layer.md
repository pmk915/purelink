# Retrieval Layer

The retrieval layer lives under `app/services/retrieval/`.

Its public entrypoint is:

```python
retrieval_service.retrieve(request: RetrievalRequest) -> RetrievalResult
```

## Core Types

- `RetrievalRequest`: query, KB id, user id, mode, top_k, permission context, DB/session internals.
- `RetrievalMode`: `auto`, `chunk_only`, `overview`, `graph_vector_mix`, `hybrid_text`, plus future placeholders.
- `RetrievedEvidence`: normalized citation-ready evidence with document/chunk/citation ids and scores.
- `RetrievalResult`: final evidence list, context text, reranker usage, trace id, and compatibility metadata.

## Modes

- `AUTO`: rule-based query router that selects a concrete retrieval mode before lower-level retrieval runs.
- `CHUNK_ONLY`: vector/hybrid chunk retrieval with citation unit selection.
- `OVERVIEW`: adapter around the existing overview retrieval flow.
- `GRAPH_VECTOR_MIX`: merges graph-derived candidates with vector candidates, then reuses final evidence selection and optional reranker.
- `HYBRID_TEXT`: merges vector candidates with deterministic keyword candidates for API paths, config keys, file names, commands, error codes, and migration ids.

Unsupported future modes fallback to `CHUNK_ONLY`.

`AUTO` never reaches the lower-level retrieval implementation. `retrieval_service.retrieve()` records `requested_mode`, `selected_mode`, `router_reason`, and `router_type` in result/trace metadata, then calls the existing concrete mode implementation.

`HYBRID_TEXT` is a lightweight local retrieval mode. It is not an Elasticsearch/OpenSearch integration and does not replace vector retrieval; it adds lexical candidates before the existing reranker and citation pipeline.

## Why This Exists

QA generation should not own retrieval details. The QA service asks for evidence and context; the retrieval layer owns candidate retrieval, graph merge, reranking, trace, and citation-ready evidence construction.
