# Lightweight GraphRAG

PureLink includes a lightweight GraphRAG prototype inspired by LightRAG.

It is not a full LightRAG implementation and does not use an external graph database.

## Storage

Graph data is stored in PostgreSQL:

- `knowledge_entities`
- `knowledge_relations`
- `entity_mentions`

Relations and mentions are grounded to source document/chunk/citation-unit records when available.

The current schema does not have a separate `relation_sources` table. Each
`knowledge_relations` row is a source-grounded relation evidence row. Export and
debug views group rows with the same source entity, target entity, relation type,
and description into a logical relation with multiple sources.

## Extraction

M7 uses a deterministic local rule extractor. It extracts simple entities and relations from chunks and citation units.

Graph extraction writes `document_indexes.graph` status:

- `indexing`
- `indexed`
- `failed`

Graph extraction failure does not break normal vector RAG.

## Lifecycle Maintenance

M17 adds lifecycle cleanup for the lightweight graph:

- `delete_document_graph(document_id)` removes mentions and relation evidence rows contributed by one document, then removes orphan entities in the same KB.
- `rebuild_document_graph(document_id)` deletes that document's graph evidence, rebuilds graph data from existing chunks/citation units, deduplicates exact duplicate relation evidence, and cleans orphan entities. It does not parse the original file, rechunk, or rebuild the vector index.
- `cleanup_orphan_entities(kb_id)` deletes entities that have no mentions and are not used as either side of a relation.
- `deduplicate_relations(kb_id)` removes exact duplicate relation evidence rows. Distinct source documents/chunks are preserved so relation provenance is not lost.
- `export_graph(kb_id)` returns bounded JSON with entities, grouped relations, source counts, and short evidence snippets. It also supports entity search, relation-type filtering, and one-hop entity neighborhoods for the Graph Explorer UI.

Document deletion calls graph cleanup before deleting the document record, so
graph data should not leave obvious stale mentions or relation evidence after a
document is removed.

## Retrieval

`RetrievalMode.GRAPH_VECTOR_MIX`:

```text
query -> vector candidates -> query entity match -> graph candidates
  -> merge/dedup -> optional rerank -> final evidence
```

Graph candidates can populate `RetrievedEvidence.graph_score`.

## API and Permissions

Personal KB graph maintenance:

- `POST /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/graph/rebuild`
- `POST /api/v1/knowledge-bases/{kb_id}/graph/cleanup-orphans`
- `POST /api/v1/knowledge-bases/{kb_id}/graph/deduplicate-relations`
- `GET /api/v1/knowledge-bases/{kb_id}/graph/export`

Team KB graph maintenance follows the existing team KB route shape:

- `POST /api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents/{document_id}/graph/rebuild`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/cleanup-orphans`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/deduplicate-relations`
- `GET /api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/export`

The export endpoints accept:

- `q`: case-insensitive entity search across name, normalized name, type, and description.
- `relation_type`: exact normalized relation type filter.
- `entity_id`: returns relations directly connected to that entity and the neighboring entities.
- `limit_entities`, `limit_relations`, `limit_sources_per_relation`: bounded result controls for UI/debug use.

The response includes total and filtered counts plus `available_relation_types`
so the frontend can render filters without a separate discovery call.

Personal KB owners can run maintenance and export. Team admins can rebuild,
cleanup, and deduplicate. Team members can export/view graph data but cannot run
maintenance operations.

## Graph Explorer UI

M20 keeps Graph Explorer list-based rather than canvas-based. The workspace Graph
tab can:

- search entities
- filter by relation type
- select an entity and inspect its one-hop neighborhood
- open relation source snippets and source document metadata
- jump from a relation source to the M19 Document Processing Inspector
- download the current graph view as JSON, entities CSV, or relations CSV

Graph Explorer uses the M17 export endpoint and does not introduce a graph
database or visualization library.

## Limitations

Current GraphRAG is lightweight and evidence-grounded. It does not claim complex multi-hop graph reasoning, graph community detection, graph visualization, or full LightRAG compatibility.

Relation deduplication intentionally preserves separate evidence rows from
different source documents/chunks. This keeps provenance traceable, but it also
means the database may contain multiple rows for the same logical relation when
there are multiple sources.
