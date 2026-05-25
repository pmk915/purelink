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
