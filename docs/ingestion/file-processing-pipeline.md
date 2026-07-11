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

Plain `.txt` files normally use the flat text parser. If a TXT file has a
conservative Markdown-like structure, such as multiple headings with body text,
PureLink parses it into structured text blocks while keeping `source_type=text`.
This is intentionally conservative; not every TXT file is treated as Markdown.

## ParsedDocument

Parsers return structured blocks and backward-compatible text. `ParsedDocument.text` preserves the legacy path, while `ParsedDocument.blocks` gives chunking and future GraphRAG a structured source.

## Chunk Strategy

PureLink supports two chunk strategies:

- `fixed`: the default flat-text chunker. It preserves existing behavior.
- `block_aware`: uses persisted `DocumentBlock` records to keep headings, paragraphs, tables, and code closer to source boundaries.

The block-aware strategy is inspired by LightRAG's separation of parser output and chunking strategy, but it uses PureLink's own conservative `DocumentBlock` schema. It does not claim full LightRAG paragraph-semantic chunking parity.

## Chunks and Citation Units

Chunks are retrieval units. Citation units are finer-grained grounding units used for answer citations.

Chunk generation keeps an internal source-span mapping from chunk-local offsets
back to processed document offsets, page numbers, headings, and extractor
metadata. Citation units use those spans so they do not cross hard boundaries
such as document blocks, PDF pages, heading sections, field-like lines, or list
items. Field facts such as `声：小泽亚李` or `形似动物：兔子` are allowed to stay
short because they contain both label and value.

## Indexing

Indexing writes vector metadata to `document_indexes.vector`. After vector indexing succeeds, PureLink attempts lightweight graph indexing. Graph index failure is isolated and does not break vector RAG.

## Operational Notes

These parsing and citation-unit rules apply when a document is processed. Already
processed documents keep their existing chunks, citation units, and vector index
until they are reprocessed and reindexed. No database migration is required for
this behavior because the additional source-span data is internal to processing
and the persisted metadata uses existing JSON fields.
