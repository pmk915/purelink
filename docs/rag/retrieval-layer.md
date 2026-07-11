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

`AUTO` never reaches the lower-level retrieval implementation. The query router is deterministic and rule-based; it is not an LLM classifier or agent router.

Router priority is stable:

```text
overview > relation > exact technical identifier > chunk_only
```

The router also records `router_confidence`:

- `high`: explicit overview phrase, strong relation structure, or exact technical identifier.
- `low`: weak or ambiguous signal; the router defaults to `chunk_only`.
- `manual`: non-auto mode was explicitly requested and the router did not override it.

`selected_mode` means the routed mode. `effective_mode` means the retrieval mode actually used after fallback. For example, an `auto` query can route to `graph_vector_mix` but fall back to `chunk_only` if graph candidates are empty. This distinction lets eval measure router accuracy without treating fallback as a router classification failure.

`retrieval_service.retrieve()` records these fields in result/trace metadata:

- `requested_mode`
- `selected_mode`
- `effective_mode`
- `router_reason`
- `router_confidence`
- `router_type`
- `fallback_mode`
- `fallback_reason`

Fallback is conservative:

- `graph_vector_mix` falls back to `chunk_only` when graph retrieval fails, returns no graph candidates, or graph candidates are below the retrieval threshold.
- `hybrid_text` preserves vector candidates and records fallback when keyword retrieval fails, returns no keyword candidates, or adds no keyword signal.
- Manual modes keep their requested/selected mode and use `router_confidence=manual`.

`HYBRID_TEXT` is a lightweight local retrieval mode. It is not an Elasticsearch/OpenSearch integration and does not replace vector retrieval; it adds lexical candidates before the existing reranker and citation pipeline.

## Why This Exists

QA generation should not own retrieval details. The QA service asks for evidence and context; the retrieval layer owns candidate retrieval, graph merge, reranking, trace, and citation-ready evidence construction.
