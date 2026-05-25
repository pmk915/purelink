# Lightweight GraphRAG

PureLink includes a lightweight GraphRAG prototype inspired by LightRAG.

It is not a full LightRAG implementation and does not use an external graph database.

## Storage

Graph data is stored in PostgreSQL:

- `knowledge_entities`
- `knowledge_relations`
- `entity_mentions`

Relations and mentions are grounded to source document/chunk/citation-unit records when available.

## Extraction

M7 uses a deterministic local rule extractor. It extracts simple entities and relations from chunks and citation units.

Graph extraction writes `document_indexes.graph` status:

- `indexing`
- `indexed`
- `failed`

Graph extraction failure does not break normal vector RAG.

## Retrieval

`RetrievalMode.GRAPH_VECTOR_MIX`:

```text
query -> vector candidates -> query entity match -> graph candidates
  -> merge/dedup -> optional rerank -> final evidence
```

Graph candidates can populate `RetrievedEvidence.graph_score`.

## Limitations

Current GraphRAG is lightweight and evidence-grounded. It does not claim complex multi-hop graph reasoning, graph community detection, graph visualization, or full LightRAG compatibility.
