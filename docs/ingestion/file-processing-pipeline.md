# File Processing Pipeline

PureLink processes text-like files through a structured ingestion pipeline.

```text
upload -> storage -> parser registry -> ParsedDocument
  -> document_blocks -> normalized text -> chunks
  -> citation units -> embeddings -> vector index metadata
  -> graph index attempt
```

## Upload and Storage

Upload endpoints handle authentication, ownership/team permission, duplicate checks, file storage, and processing job creation.

## Parser Registry

Parser routing supports:

- `.txt`
- `.md`
- `.docx`
- text-based `.pdf`

Unsupported file types fail explicitly unless enabled by optional OCR/media paths.

## ParsedDocument

Parsers return structured blocks and backward-compatible text. Existing chunking continues to receive normalized text.

## Chunks and Citation Units

Chunks are retrieval units. Citation units are finer-grained grounding units used for answer citations.

## Indexing

Indexing writes vector metadata to `document_indexes.vector`. After vector indexing succeeds, PureLink attempts lightweight graph indexing. Graph index failure is isolated and does not break vector RAG.
