# PureLink Project Storyline

## 1. Problem

PureLink started from a practical problem: many RAG demos can answer a question once, but they do not expose enough engineering structure to be debugged, evaluated, or productized.

Common gaps:

- document structure is flattened before retrieval
- retrieval strategy is not explicit or comparable
- citations are fragile or delegated to the LLM
- retrieval failures require reading backend logs
- document processing failures are hard for users to diagnose
- graph data can become stale after document deletion or reindexing
- GraphRAG provenance is unclear
- there is no repeatable eval baseline

## 2. Solution Overview

PureLink addresses those gaps by treating RAG as a product workflow plus an inspectable retrieval system.

Key pieces:

- `DocumentBlock` and block-aware chunking preserve document structure such as headings, tables, and code blocks.
- Retrieval Layer separates evidence retrieval from answer generation.
- `hybrid_text` retrieval adds deterministic keyword recall for API paths, config keys, file names, commands, and error codes.
- Query Router supports `auto` mode and records `requested_mode`, `selected_mode`, and `router_reason`.
- Citation grounding keeps source evidence under backend control.
- Retrieval Trace records retrieval metadata for debugging candidates, scores, reranking, router decisions, and selected evidence.
- Lightweight GraphRAG stores entities, mentions, and source-grounded relation evidence.
- Graph lifecycle cleanup handles document deletion, rebuild, orphan cleanup, deduplication, and export.
- Document Processing Inspector shows RAG readiness without backend logs.
- Graph Explorer exposes source-grounded entity and relation inspection.
- RAG eval baseline compares chunking and retrieval modes with deterministic metrics.

## 3. Engineering Decisions

PureLink deliberately avoids several tempting but premature additions.

No Agent runtime:

- The current problem is retrieval quality, citation grounding, and observability.
- Adding agents before retrieval is inspectable would make failures harder to debug.

No LangGraph:

- The workflow is currently a clear service pipeline, not a dynamic multi-step agent graph.
- Keeping it explicit makes tests and smoke simpler.

No Neo4j or Memgraph:

- The graph is lightweight and source-grounded.
- PostgreSQL tables are enough for the current entity/relation lifecycle.

No complex graph canvas:

- The user need is inspection and provenance, not graph visualization.
- A list-based Explorer is easier to test, easier to explain, and consistent with the KB workspace.

No default multimodal RAG:

- The Core path focuses on text KBs.
- OCR, ASR, and VLM support would introduce heavier dependencies and different failure modes.

## 4. Milestone Timeline

- M1: Retrieval Layer boundary.
- M2: Model provider standardization.
- M3: Optional reranker.
- M4: Index metadata and rebuild readiness.
- M5: Retrieval trace.
- M6: DocumentBlock schema and parser routing.
- M7: Lightweight GraphRAG.
- M8: Initial RAG eval harness.
- M11-M13: smoke hardening, KB management, and workspace UX.
- M14: block-aware chunking.
- M15: hybrid text retrieval.
- M16: rule-based Query Router.
- M17: GraphRAG lifecycle cleanup.
- M18: real RAG eval baseline.
- M19: Document Processing Inspector UI.
- M20: Graph Explorer enhancement.
- M21.5: interview demo packaging and docs index.

## 5. Interview Summary

### 1-minute version

PureLink is an engineering-focused RAG knowledge base system for personal and team workspaces. The project goes beyond a basic chatbot by exposing the full RAG lifecycle: document parsing, block-aware chunking, retrieval modes, citation grounding, trace metadata, graph provenance, document readiness diagnostics, and a reproducible eval baseline. The core idea is that RAG quality should be inspectable and testable, not hidden behind a single answer string.

### 3-minute version

I built PureLink around the problems I saw in typical RAG demos. They often flatten document structure, hide retrieval behavior, let citations become unreliable, and lack any repeatable evaluation. PureLink turns those issues into explicit components.

The ingestion pipeline persists `DocumentBlock` records and can use block-aware chunking so headings, tables, and code blocks are not treated as arbitrary text. The Retrieval Layer supports multiple modes: normal chunk retrieval, overview retrieval, graph-vector mixed retrieval, hybrid keyword/vector retrieval, and an `auto` router. The system records requested and selected modes, router reason, trace id, retrieved evidence, and citation-ready context.

On the product side, the KB workspace includes Ask, Documents, Graph, Retrieval Debug, Health, and Settings. M19 added a Document Processing Inspector so users can see whether a document is RAG-ready. M20 added a list-based Graph Explorer for entity search, relation filtering, one-hop neighborhoods, source inspection, and graph export.

The eval baseline compares fixed chunking, block-aware chunking, hybrid text, graph-vector mix, and auto mode across 20 repository-doc cases. The important point is not that every mode wins. The important point is that the tradeoffs are visible and reproducible.

### 5-minute version

PureLink started as a text knowledge base with authentication, personal KBs, team KBs, document upload, and RAG Q&A. The RAG v2 work moved it toward an engineering system rather than a demo.

First, I separated retrieval from answer generation. That created a stable Retrieval Layer with typed requests, evidence, modes, context building, and citation building. Then I standardized model providers so embedding, reranker, and LLM choices do not leak into business logic. After that, I added optional reranking, index metadata, and retrieval trace so retrieval quality and index compatibility could be inspected.

The ingestion side then moved from flat text toward structured blocks. Documents are parsed into blocks such as headings, text, tables, and code. Block-aware chunking can use those boundaries to preserve structure. This was important because many RAG failures start before retrieval, when the document is split badly.

For retrieval, I added `hybrid_text` for exact technical tokens and a rule-based `auto` router. The router is intentionally simple: it does not use an LLM or agent. It routes technical/config/path-like queries to `hybrid_text`, relationship queries to `graph_vector_mix`, overview queries to `overview`, and defaults to `chunk_only`.

For GraphRAG, I kept the graph lightweight. It uses PostgreSQL tables for entities, mentions, and relations. Relations are source-grounded, and lifecycle operations can clean document graph data, rebuild one document's graph, remove orphan entities, deduplicate relation evidence, and export bounded graph JSON. The Graph Explorer exposes this graph as a diagnostic tool, not a visual graph canvas.

Finally, I added productized debugging and evaluation. Document Processing Inspector shows block/chunk/citation/vector/graph status and copyable debug JSON. Retrieval Debug and Retrieval Details expose mode and trace behavior. The eval baseline runs real repository-doc cases and reports retrieval hit, citation hit, top-k doc hit, keyword coverage, trace availability, and selected modes.

The result is a project that can be discussed as a RAG engineering platform: not production SaaS, not a full LightRAG clone, but a clear demonstration of how to make RAG systems observable, maintainable, and evaluable.
