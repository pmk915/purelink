# Knowledge Base Workspace

M13 organizes each knowledge base as a RAG workspace rather than a single ask page.

## Tabs

- Ask: ask questions, inspect the current answer, and review supporting evidence.
- Documents: upload, process, retry, preview, and delete documents where permitted.
- Graph: browse lightweight entities, mentions, and source-grounded relations.
- Retrieval Debug: owner/admin tool for direct retrieval inspection.
- Health: document, vector index, and graph index status summary.
- Settings: metadata and safe destructive actions.

## Document Processing Inspector

M19 adds a document status dialog from the Documents tab. Each document row has
a status/debug entry that opens a compact inspector with:

- processing status and RAG-ready badge
- block, chunk, citation-unit, vector-index, and graph-index counts
- pipeline checks for processing, document blocks, chunks, citation units, vector index, and graph index
- warning and error details, including latest processing step and error code/message when available
- copyable debug JSON for support and troubleshooting

Base RAG readiness requires chunks, citation units, and a ready compatible vector
index. Graph index status is shown because it affects Graph Explorer and
`graph_vector_mix`, but a missing graph index is treated as optional and does not
block base Q&A readiness.

## Graph Maintenance

The backend now supports lightweight GraphRAG lifecycle operations:

- Rebuild a single document graph from existing chunks and citation units.
- Cleanup orphan entities that no longer have mentions or relations.
- Deduplicate exact duplicate relation evidence rows.
- Export bounded graph JSON for debugging and interview demos.

Deleting a document also cleans the graph mentions and relation evidence
contributed by that document before the document row is removed.

## Permission Model

- Personal KB owner can access all tabs.
- Personal KB owner can view document status/debug.
- Personal KB owner can run graph maintenance.
- Team admin can access all tabs and run graph maintenance.
- Team member can access Ask, Documents, Graph, and Health, export/view graph data, and view document status/debug.
- Team member cannot rebuild graph, cleanup orphan entities, or deduplicate relations.
- Backend permission checks remain authoritative.

## LightRAG-inspired Boundary

The workspace borrows LightRAG-style information architecture around document indexing, graph exploration, and RAG query/debug surfaces. It does not implement full LightRAG graph reasoning, external graph storage, or a complex graph visualization canvas.

## Retrieval Debug Modes

Retrieval Debug can compare:

- `auto`: rule-based router that chooses a concrete retrieval mode from the query.
- `chunk_only`: normal chunk/vector retrieval.
- `overview`: broad knowledge-base overview retrieval.
- `graph_vector_mix`: lightweight graph candidates plus vector candidates.
- `hybrid_text`: keyword candidates plus vector candidates.

Use `hybrid_text` for exact technical terms such as API paths, config keys, file names, commands, error codes, and migration identifiers.
Use `auto` to inspect the backend-selected retrieval mode and router reason without manually choosing a mode.
