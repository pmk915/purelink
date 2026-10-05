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

## Native PDF Extraction

Native born-digital PDF text uses PyMuPDF `page.get_text("blocks", sort=True)`.
Each retained text block becomes a `DocumentBlock.TEXT`, ordered first by
physical page and then by PyMuPDF's supported block ordering. Empty blocks and
image descriptions are excluded. Existing text normalization and processed-text
character ranges are retained; identifiers such as `RETRIEVAL_MIN_SCORE` and
`graph_vector_mix` remain intact.

PDF blocks carry `source_type=pdf`, `extractor=pymupdf`, a physical one-based
`page_number`, the existing `page:N` source locator, and `bbox` metadata.
The bbox is a JSON array of four finite floating-point coordinates
`[x0, y0, x1, y1]` in PyMuPDF page coordinates (points, with a top-left origin).
It describes the extracted block, not individual citation sentences. Bboxes are
persisted in existing block JSON metadata; they are not a new retrieval evidence
or source-preview contract. `order_index` records stable retained-block order.
Empty pages do not emit text blocks, but subsequent page numbers are not shifted.

This is lightweight supporting infrastructure for retrieval and citation
grounding. Limitations are deliberate:

- `sort=True` does not guarantee perfect multi-column reading order.
- No advanced heading hierarchy or font-based heading inference.
- No dedicated table structure extraction; tables remain extracted text blocks.
- OCR fallback remains optional and disabled by default (`ENABLE_OCR=false`).
  Its existing document-level quality checks and provider behavior are unchanged;
  mixed native/scanned-page completeness is not guaranteed.
- Complex document understanding systems such as Docling are outside Core scope.

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

Fixed PDF chunks preserve page boundaries. Block-aware chunks may contain text
from multiple pages. Such chunks omit singular `page_number` and `source_locator`
metadata and retain their per-page `source_locators` and internal source spans.
Citation units recover the precise originating `page:N` from those spans, and
that page provenance survives into final `RetrievalResult.evidences`.

Inline Markdown cleanup removes paired presentation markers without changing
technical identifiers such as `RETRIEVAL_MIN_SCORE`, `graph_vector_mix`, or
`__init__`. Citation sentence boundaries also preserve periods inside decimals,
versions, IP addresses, filenames, and module paths while retaining accurate
processed-source character spans.

## Indexing

Indexing writes vector metadata to `document_indexes.vector`. After vector indexing succeeds, PureLink attempts lightweight graph indexing. Graph index failure is isolated and does not break vector RAG.

## Operational Notes

These parsing and citation-unit rules apply when a document is processed. Already
processed documents keep their existing chunks, citation units, and vector index
until they are reprocessed and reindexed. No database migration is required for
this behavior because the additional source-span data is internal to processing
and the persisted metadata uses existing JSON fields.
