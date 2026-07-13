# Document Processing and Chunking

## Purpose

This guide explains how PureLink converts supported files into persisted document structure, retrieval chunks, and smaller citation units while preserving source provenance.

## 30-second interview answer

PureLink parses a file into ordered `DocumentBlock` records before chunking so headings, pages, tables, code, fields, and source ranges remain available after text extraction. The default `fixed` strategy groups extracted segments into roughly 1,200-character chunks, while `block_aware` groups blocks under heading scopes and isolates tables and code. Citation units are then split inside source-span boundaries, giving answer generation smaller evidence with stable page, section, or character locators.

## Problem Being Solved

Flattening a file directly into arbitrary character windows loses information needed later:

- a heading may no longer identify the section containing a fact;
- a PDF chunk can blur page provenance;
- a table row or configuration field can be mixed with unrelated prose;
- an answer may need one sentence, while retrieval needs a larger semantic window;
- a citation needs a stable source range even when its parent chunk is reranked.

`DocumentBlock` is the durable intermediate representation that keeps parser structure separate from chunking policy.

## End-to-End Flow

```text
stored upload
  -> get_parser(filename, MIME type)
  -> ParsedDocument(text, blocks, metadata)
  -> assign_block_char_ranges()
  -> replace_document_blocks()
  -> chunk_document_for_processing()
  -> build_citation_unit_payloads()
  -> filter_generated_citation_units()
  -> replace_document_chunks()
  -> vector and graph indexing job
```

[`get_parser()`](../../../app/services/document_parsing/parser_registry.py) checks registered parsers in order. Selection currently depends on the filename suffix; the parser protocol also accepts MIME type. The standard registry contains `TextParser`, `MarkdownParser`, `DocxParser`, and `PdfTextParser`.

### Current format boundaries

| Format | Parser | Current behavior |
|---|---|---|
| `.txt` | `TextParser` | Decodes UTF-8/UTF-8-SIG/GB18030. Conservatively recognizes Markdown-like structure only when multiple headings and body text are present; `source_type` remains `text`. |
| `.md` | `MarkdownParser` | Produces heading, text/list, table, and fenced-code blocks with heading metadata. |
| `.docx` | `DocxParser` (`minimal_docx_text`) | Extracts WordprocessingML paragraph text and heading styles; it is not a full layout renderer. |
| `.pdf` | `PdfTextParser` | Uses the current PDF text extraction path, normally PyMuPDF, preserving page segments. Scanned-PDF OCR fallback requires OCR to be explicitly enabled and a usable provider. |

Image/audio/video extraction helpers exist behind feature settings, but they are not registered in the standard parser registry used by `process_document()` and are outside this standard four-format path.

### Why blocks come first

The parser contract returns [`ParsedDocument`](../../../app/services/document_parsing/types.py) with a list of typed `DocumentBlock` values. [`assign_block_char_ranges()`](../../../app/services/document_parsing/block_normalizer.py) assigns ranges against the normalized plain-text representation. [`replace_document_blocks()`](../../../app/services/document_parsing/block_persistence.py) persists the result before chunking.

The database [`DocumentBlock`](../../../app/models/document_block.py) stores:

- `document_id`, `order_index`, and `block_type`;
- block text and optional `heading_level`;
- a compact `source_locator`;
- `metadata_json`, including available source type, heading path, section, page, extractor, line role, and normalized character range.

## Core Data Structures

- [`DocumentBlock`](../../../app/services/document_parsing/types.py): parser-level Pydantic block.
- [`DocumentBlock` ORM model](../../../app/models/document_block.py): persisted ordered block.
- [`ChunkDraft` and `ChunkSourceSpan`](../../../app/services/document_chunking/types.py): block-aware chunk text plus local-to-source provenance.
- [`DocumentChunk`](../../../app/models/document_chunk.py): persisted retrieval window.
- [`DocumentCitationUnit`](../../../app/models/document_citation_unit.py): persisted fine-grained evidence with parent chunk and metadata.
- `GeneratedChunkPayload` and `GeneratedCitationUnitPayload` in [`document_processing.py`](../../../app/services/document_processing.py): write-boundary payloads.

### Fixed vs block-aware

| Concern | `fixed` | `block_aware` |
|---|---|---|
| Input | Extracted source segments | Persisted ordered blocks |
| Default | Yes (`CHUNK_STRATEGY=fixed`) | Opt-in |
| Size target | 1,200 chars with 120-char overlap for oversized segments | 900 target, 1,400 max by default |
| Heading handling | Heading text participates in normalized extracted text; metadata depends on source segments | Heading blocks update a heading stack; section chunks carry `heading_path` and `section_title` |
| Tables | Follows extracted segment boundaries | Standalone chunks, up to the separate table limit |
| Code | Follows extracted segment boundaries | Standalone chunks; no overlap between code split parts |
| Pages/time ranges | `should_preserve_source_boundaries()` prevents incompatible segments from being combined | Source spans preserve block/page/time metadata; blocks are grouped only by the chunker rules |
| Oversized content | Splits a large segment into fixed windows with overlap | Tries line boundaries, then paragraphs, then bounded character windows with configured overlap |
| Short tail | Normal fixed packing | May merge a short tail with the prior chunk when the parent heading scope matches |
| Failure | Processing fails if no valid chunk is produced | Logs and falls back to fixed if block-aware returns no chunks or raises |

The fixed size and overlap are current module constants (`DEFAULT_CHUNK_SIZE=1200`, `DEFAULT_CHUNK_OVERLAP=120`). Block-aware sizing is configurable.

### Markdown example

Input:

```markdown
# Retrieval

CHUNK_STRATEGY: fixed

## Supported strategies

- fixed uses character windows.
- block_aware preserves block boundaries.
```

A representative structured path is:

```text
blocks
  0 heading(level=1, text="Retrieval")
  1 text(line_role=field, section="Retrieval", text="CHUNK_STRATEGY: fixed")
  2 heading(level=2, text="Supported strategies")
  3 text(line_role=list_item, heading_path=["Retrieval", "Supported strategies"], ...)
  4 text(line_role=list_item, heading_path=["Retrieval", "Supported strategies"], ...)

block-aware chunks
  section="Retrieval": "CHUNK_STRATEGY: fixed"
  section="Supported strategies": "fixed uses ...\n\nblock_aware preserves ..."

citation units
  "CHUNK_STRATEGY: fixed"
  "fixed uses character windows."
  "block_aware preserves block boundaries."
```

Exact unit grouping still obeys configured length and sentence limits. The important invariant is that heading, field/list role, and source spans constrain grouping; the heading metadata supplies context without being copied into every displayed citation.

### Chunk vs citation unit

A chunk is the retrieval window: it is large enough for embedding, keyword matching, graph extraction, and context ranking. A citation unit is the answer evidence window: it is generated from a chunk but split along source spans, fields/list items, sentences, clauses, and configured limits.

[`build_boundary_aware_citation_units_for_chunk()`](../../../app/services/document_processing.py) does not emit heading-only source spans. Field and list lines become hard groups. A unit carries its persisted id, parent chunk key, source range, page/section/heading metadata, and source locator. This allows the UI to quote one fact rather than the whole retrieval chunk.

Technical values are protected in two ways. Structured parsing's Markdown normalization avoids treating underscores inside identifiers as emphasis. Sentence splitting checks technical-token dots and keeps alphanumeric, underscore, and hyphen characters together, so values such as `CHUNK_STRATEGY`, `block_aware`, and `0.15` are not split merely because they contain technical punctuation.

### Configuration and current defaults

| Key | Default | Used for |
|---|---:|---|
| `CHUNK_STRATEGY` | `fixed` | Select fixed or block-aware processing |
| `BLOCK_CHUNK_TARGET_CHARS` | `900` | Preferred section chunk size |
| `BLOCK_CHUNK_MAX_CHARS` | `1400` | Maximum ordinary/code block-aware size |
| `BLOCK_CHUNK_MIN_CHARS` | `120` | Short-tail merge threshold |
| `BLOCK_CHUNK_TABLE_MAX_CHARS` | `1800` | Standalone table limit |
| `BLOCK_CHUNK_OVERLAP_CHARS` | `120` | Oversized prose fallback overlap |
| `CITATION_UNIT_MIN_CHARS` | `40` | Best-effort minimum during sentence grouping |
| `CITATION_UNIT_TARGET_CHARS` | `120` | Preferred unit size |
| `CITATION_UNIT_MAX_CHARS` | `300` | Maximum unit size |
| `CITATION_UNIT_MAX_SENTENCES` | `3` | Maximum grouped sentence count |
| `ENABLE_OCR` | `false` | Enables configured OCR paths |
| `OCR_PROVIDER` | `disabled` | Default OCR provider state |

Defaults are defined in [`get_settings()`](../../../app/core/config.py) and mirrored in [`.env.example`](../../../.env.example).

## Verified Code Entry Points

- Parsing: [`parser_registry.py`](../../../app/services/document_parsing/parser_registry.py), [`structured_text.py`](../../../app/services/document_parsing/structured_text.py), and the [`parsers`](../../../app/services/document_parsing/parsers/) directory.
- Persistence: [`block_persistence.py`](../../../app/services/document_parsing/block_persistence.py), [`replace_document_chunks()`](../../../app/services/document_processing.py).
- Chunking: [`chunk_document_for_processing()`](../../../app/services/document_processing.py), [`build_block_aware_chunks()`](../../../app/services/document_chunking/block_aware_chunker.py).
- Citation splitting: [`build_citation_unit_payloads()`](../../../app/services/document_processing.py), [`split_text_into_sentence_spans()`](../../../app/services/document_processing.py).
- Design context: [Document Blocks](../../ingestion/document-blocks.md) and [File Processing Pipeline](../../ingestion/file-processing-pipeline.md).

## Failure and Fallback Behavior

- Unsupported suffixes and parser misses produce processing errors before persistence completes.
- Text quality checks reject empty, binary-like, garbled, or null-containing chunk content.
- PDF extraction distinguishes missing/garbled text and can attempt OCR only when configured; default local behavior does not require OCR.
- Block-aware exceptions or empty output fall back to fixed chunking and log the event.
- Chunk and citation-unit replacement deletes prior rows for that document and writes the new set in one processing transaction.
- Retryable persistence/unexpected processing errors may be requeued; known unsupported or low-quality inputs are non-retryable.
- Vector indexing is a later job, so parsed content may exist while RAG readiness remains false.

## Tests and Verification

- [`tests/services/document_parsing/test_parser_registry.py`](../../../tests/services/document_parsing/test_parser_registry.py): parser selection and unsupported formats.
- [`tests/services/document_parsing/test_structured_text.py`](../../../tests/services/document_parsing/test_structured_text.py): conservative Markdown-like TXT detection and identifier preservation.
- [`tests/services/document_chunking/test_block_aware_chunker.py`](../../../tests/services/document_chunking/test_block_aware_chunker.py): headings, tables, code, source spans, limits, and fallback splitting.
- [`tests/services/document_parsing/test_processing_integration.py`](../../../tests/services/document_parsing/test_processing_integration.py): parse-to-database round trips for TXT and PDF strategies.
- [`tests/test_citation_units.py`](../../../tests/test_citation_units.py): unit grouping, locators, ranges, and technical token behavior.

## Design Trade-offs

- Persisting blocks adds rows and processing work, but decouples parser structure from future chunk strategies.
- Fixed chunking is predictable and remains the default; block-aware gives better structural provenance but depends on parser quality.
- Citation units improve precision but add a second evidence granularity and require old documents to be refreshed after splitting changes.
- Rule-based PDF and DOCX extraction is inspectable and lightweight, but does not reconstruct complex visual layout.

## Known Limitations

- Multi-column and heavily positioned PDFs may have imperfect reading order.
- Scanned PDFs need an explicitly enabled OCR provider; OCR is disabled by default.
- DOCX extraction does not preserve every style, drawing, embedded object, or complex table layout.
- Cross-page tables are not reconstructed as one semantic table.
- Block-aware quality cannot exceed the structure emitted by the parser.
- Previously processed documents do not automatically gain newer citation normalization or unit boundaries. They require reprocessing and vector reindexing; no database migration is required.

## Common Interview Follow-ups

**Why not embed each block directly?** Individual blocks can be too small for semantic retrieval. Chunks group related blocks while retaining source spans back to each block.

**Why is fixed still the default?** It is the compatibility baseline and has fewer assumptions about parser structure. Block-aware is opt-in and falls back safely.

**Are headings included in citation text?** Heading-only spans are filtered; heading path and section title remain metadata used for context and navigation.

**Can a citation cross PDF pages?** Boundary-aware units are built from source spans carrying page metadata, so a unit stays within its source span rather than merging arbitrary pages.

**Does `min_chars=40` delete short facts?** No. It is a grouping target, not a blanket deletion rule; valid short field facts can remain.

**Why reprocess old documents?** Citation units are persisted artifacts. Code changes do not rewrite existing rows or their vector index automatically.

## Concise Answer Examples

**DocumentBlock:** "It is the persisted structural boundary between format-specific parsing and strategy-specific chunking."

**Two granularities:** "Chunks optimize recall and context; citation units optimize evidence precision and source navigation."

**Compatibility:** "Block-aware is configurable and best-effort; failure falls back to the existing fixed path."
