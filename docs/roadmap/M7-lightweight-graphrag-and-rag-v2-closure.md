# PureLink M7 Upgrade Plan: RAG v2 Core Closure and Lightweight GraphRAG

## Goal

M7 closes the current RAG v2 Core documentation and adds a lightweight GraphRAG extension.

The GraphRAG scope is intentionally small:

- store entities, relations, and entity mentions in PostgreSQL
- extract them with a deterministic local rule extractor
- keep relations grounded to document/chunk/citation-unit sources
- add `graph_vector_mix` retrieval as an optional mode

M7 does not add Neo4j, full LightRAG compatibility, complex multi-hop reasoning, graph visualization, Agent runtime, or multimodal parsing.

## RAG v2 Closure

The RAG v2 Core is documented in `docs/architecture/rag-v2-architecture.md`.

It covers:

- parser registry and document blocks
- chunks and citation units
- embedding provider and index metadata
- retrieval layer and optional reranker
- retrieval trace
- lightweight RAG evaluation
- known non-claims and SQLite migration note

## Lightweight GraphRAG

M7 adds:

- `knowledge_entities`
- `knowledge_relations`
- `entity_mentions`
- local rule graph extraction
- `document_indexes.graph` status updates
- graph-vector mixed retrieval

Graph extraction runs after vector indexing succeeds. Failure is contained to the graph index and does not break normal vector RAG.

## Validation

Expected validation:

```bash
.venv/bin/python -m pytest tests/services/knowledge_graph tests/models/test_knowledge_graph.py
.venv/bin/python -m pytest tests/services/retrieval tests/test_retrieval_pipeline.py
.venv/bin/python -m pytest tests/services/document_parsing tests/services/indexing
.venv/bin/python -m pytest tests/eval
make test
make smoke-docx-rag
git diff --check
```

## Design Principle

PureLink should become LightRAG-inspired, not a LightRAG clone.

Graph candidates augment vector candidates, and final answers remain citation-grounded.
