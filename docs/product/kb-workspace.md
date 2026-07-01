# Knowledge Base Workspace

M13 organizes each knowledge base as a RAG workspace rather than a single ask page.

## Tabs

- Ask: ask questions, inspect the current answer, and review supporting evidence.
- Documents: upload, process, retry, preview, and delete documents where permitted.
- Graph: browse lightweight entities, mentions, and source-grounded relations.
- Retrieval Debug: owner/admin tool for direct retrieval inspection.
- Health: document, vector index, and graph index status summary.
- Settings: metadata and safe destructive actions.

## Permission Model

- Personal KB owner can access all tabs.
- Team admin can access all tabs.
- Team member can access Ask, Documents, Graph, and Health.
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
