# Retrieval Trace

Retrieval trace makes RAG behavior observable.

Tables:

- `retrieval_traces`
- `retrieval_trace_items`

## Trace Header

Records:

- query
- retrieval mode
- top_k
- user and KB ids
- embedding provider/model
- reranker provider/model
- initial candidate count
- final evidence count
- duration and metadata

The metadata JSON also records routing and answer-support decisions when
available:

- `requested_mode`, `selected_mode`, `effective_mode`
- `router_reason`, `router_confidence`
- `routing_query_source` (`evidence_query` or `query`)
- `fallback_mode`, `fallback_reason`
- `answerable`
- `evidence_support_score`
- `evidence_support_reason`
- `evidence_support_query_type`
- `evidence_support_signals`
- `supporting_evidence_ids`

Conversation retrieval traces also carry `conversation_id`. The trace header
keeps the actual retrieval query, while `routing_query_source` records which
request field drove the rule-based router without duplicating the current user
question in metadata. A message id is not fabricated before message
persistence.

## Trace Items

Each item can record:

- document/chunk/citation-unit references
- candidate preview
- vector score
- graph score
- rerank score
- final rank
- `selected_for_context`
- filtered reason
- index compatibility metadata

## Debugging Use

Trace helps determine whether a bad answer came from parsing, chunking,
retrieval recall, reranking, stale index filtering, citation selection, evidence
support gating, or answer generation.
