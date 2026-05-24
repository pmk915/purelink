# PureLink M4 Upgrade Plan: Index Version and Rebuild Readiness

## Goal

M4 makes vector indexing explicit. PureLink records which embedding provider, model, dimension, and version produced a document's vector index so later model switches can be detected before retrieval mixes incompatible embedding spaces.

## Scope

- Add `document_indexes` for per-document index metadata.
- Support `vector` index metadata now, while reserving `graph` and `lexical` index types.
- Track `pending`, `indexing`, `indexed`, `stale`, and `failed` index states.
- Write vector index metadata from the existing document indexing pipeline.
- Detect compatibility against the current embedding provider/model/dimension.
- Keep legacy documents without metadata retrievable for backward compatibility.

## Non-goals

- Do not switch the default embedding model.
- Do not add GraphRAG, DocumentBlock, retrieval trace tables, or a rebuild UI.
- Do not make old documents unretrievable just because they predate M4 metadata.
- Do not change frontend behavior unless a later rebuild workflow needs it.

## Design

`document_indexes` stores one row per document and index type:

- `document_id`
- `knowledge_base_id`
- `index_type`
- `provider`
- `model_name`
- `model_dim`
- `model_version`
- `status`
- `error_message`
- `stale_reason`
- `indexed_at`

The document processing lifecycle still belongs to `documents.processing_status`. The index lifecycle belongs to `document_indexes.status`.

## Retrieval Compatibility

Retrieval allows documents without index metadata as `legacy_unknown` so existing knowledge bases continue to work. If metadata exists, retrieval only uses rows that are `indexed` and match the current embedding provider, model, and known dimension.

## Rebuild Readiness

M4 includes service hooks for future rebuild workflows:

- mark vector index as `pending`
- mark vector index as `indexing`
- mark vector index as `indexed`
- mark vector index as `failed`
- mark vector index as `stale`

M5 can build retrieval trace on this foundation. A later rebuild milestone can enqueue reindex jobs using these statuses.
