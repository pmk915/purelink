# File Processing Pipeline

PureLink processes text-like files through a structured ingestion pipeline.

```text
upload -> storage -> parser registry -> ParsedDocument
  -> document_blocks -> chunk strategy -> chunks
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

Parsers return structured blocks and backward-compatible text. `ParsedDocument.text` preserves the legacy path, while `ParsedDocument.blocks` gives chunking and future GraphRAG a structured source.

## Chunk Strategy

PureLink supports two chunk strategies:

- `fixed`: the default flat-text chunker. It preserves existing behavior.
- `block_aware`: uses persisted `DocumentBlock` records to keep headings, paragraphs, tables, and code closer to source boundaries.

The block-aware strategy is inspired by LightRAG's separation of parser output and chunking strategy, but it uses PureLink's own conservative `DocumentBlock` schema. It does not claim full LightRAG paragraph-semantic chunking parity.

## Chunks and Citation Units

Chunks are retrieval units. Citation units are finer-grained grounding units used for answer citations.

## Indexing

Indexing writes vector metadata to `document_indexes.vector`. After vector indexing succeeds, PureLink attempts lightweight graph indexing. Graph index failure is isolated and does not break vector RAG.
