# RAG Answer Experience

PureLink answers are designed to show why an answer is grounded in the knowledge base.

## Answer Surface

The conversation view shows:

- assistant answer text
- citation/evidence panel
- citation marker such as `[S1]`
- source document name
- source locator when available
- evidence snippet
- source preview link when the citation can be opened

## Retrieval Details

The UI includes a collapsed retrieval details section near citations. It currently shows frontend-visible evidence metadata, such as evidence count. More fields such as `trace_id`, retrieval mode, and reranker usage can be added when the backend response exposes them to persisted conversation messages.

## Knowledge Base Health

The knowledge base workspace shows a compact health summary:

- document count
- ready/failed/preparing document counts
- vector index status counts
- graph index status counts when graph index metadata exists

This helps users understand whether a knowledge base is ready for Q&A before debugging answer quality.
