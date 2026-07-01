# Knowledge Base Workspace

M13 organizes each knowledge base as a RAG workspace rather than a single ask page.

## Tabs

- Ask: ask questions, inspect the current answer, and review supporting evidence.
- Documents: upload, process, retry, preview, and delete documents where permitted.
- Graph: browse lightweight entities and source-grounded relations.
- Retrieval Debug: owner/admin tool for direct retrieval inspection.
- Health: document, vector index, and graph index status summary.
- Settings: metadata and safe destructive actions.

For a step-by-step interview walkthrough, use
[PureLink Interview Demo Guide](../interview/purelink-demo-guide.md). For a
feature-to-code map, use [Feature Map](../interview/feature-map.md).

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

If status loading fails, the dialog uses the shared error state and displays the
backend error message, code, and request id when available. The request id is the
safe handoff value for backend log lookup.

## Upload Limits and Validation

The Documents tab upload card shows the active upload policy from
`GET /api/v1/upload/constraints`.

Current default policy:

- supported types: PDF, DOCX, Markdown, TXT
- max size: 25 MB
- empty files are rejected
- unsafe filenames are rejected, including blank names, path separators, null bytes, and names longer than 255 characters

The frontend checks file size, extension, empty files, and filename shape before
submitting. The backend repeats the validation for personal and team KB uploads
and returns the M21.1 error envelope with codes such as `UPLOAD_TOO_LARGE`,
`UNSUPPORTED_FILE_TYPE`, and `VALIDATION_ERROR`.

## Error, Empty, and Loading States

M21.1 standardizes the workspace failure states:

- KB load failures show a compact error panel with retry.
- Documents tab uses a shared empty state for an empty KB and a shared error state for document-list load failures.
- Document Processing Inspector, Graph Explorer, Ask, and Retrieval Debug display backend error code/request id when the API provides them.
- Graph Explorer uses shared empty states for no graph data and no matching relations.

These states intentionally reuse the existing cards, badges, muted borders, and
button sizes so error handling feels like part of the workspace instead of a
separate debug UI.

## Graph Maintenance

The backend now supports lightweight GraphRAG lifecycle operations:

- Rebuild a single document graph from existing chunks and citation units.
- Cleanup orphan entities that no longer have mentions or relations.
- Deduplicate exact duplicate relation evidence rows.
- Export bounded graph JSON for debugging and interview demos.

Deleting a document also cleans the graph mentions and relation evidence
contributed by that document before the document row is removed.

## Graph Explorer

M20 enhances the Graph tab as a compact diagnostic explorer rather than a graph
canvas. It supports:

- entity search
- relation type filtering
- one-hop neighborhood inspection after selecting an entity
- relation source inspection with filenames, chunk/citation-unit ids, and short snippets
- opening the M19 Document Processing Inspector from a relation source document
- exporting the current graph view as JSON, entities CSV, or relations CSV

The UI intentionally uses the same cards, badges, muted borders, and compact
actions as the rest of the KB workspace. It avoids canvas visualization and large
new frontend dependencies.

In interviews, Graph Explorer is best framed as a provenance and debugging
surface. Show entity search, relation type filtering, one-hop neighborhood,
source snippets, and the jump from a relation source to Document Processing
Inspector. Do not describe it as a full graph visualization or multi-hop graph
reasoning system.

## Permission Model

- Personal KB owner can access all tabs.
- Personal KB owner can view document status/debug.
- Personal KB owner can run graph maintenance.
- Team admin can access all tabs and run graph maintenance.
- Team member can access Ask, Documents, Graph, and Health, export/view graph data, inspect relation sources, and view document status/debug.
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

## Demo Entry Points

- Ask tab: show citations, Retrieval Details, selected mode, and trace id.
- Documents tab: open Document Processing Inspector and copy debug info.
- Graph tab: inspect relation sources and export graph JSON/CSV.
- Retrieval Debug tab: compare `chunk_only`, `hybrid_text`, `graph_vector_mix`, and `auto`.
- Health tab: verify document, vector index, and graph index readiness.
