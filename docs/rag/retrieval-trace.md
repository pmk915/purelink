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

Trace helps determine whether a bad answer came from parsing, chunking, retrieval recall, reranking, stale index filtering, citation selection, or answer generation.
