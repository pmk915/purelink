# PureLink M6 Upgrade Plan: Document Block Schema and Parser Routing

## Goal

M6 upgrades document ingestion from a plain-text-only parse result to a structured block representation:

```text
document -> blocks -> plain text compatibility -> chunks -> citation units -> embeddings
```

The objective is to preserve current RAG behavior while preparing the ingestion layer for better chunking, citation precision, table handling, GraphRAG extraction, and future multimodal placeholders.

## Scope

M6 adds:

- `DocumentBlockType`, `DocumentBlock`, and `ParsedDocument` service types.
- Parser routing for `.txt`, `.md`, `.docx`, and text-based `.pdf`.
- Parsers that return structured blocks plus backward-compatible plain text.
- A block normalizer that converts blocks back to the text form used by existing chunking.
- Persisted `document_blocks` records for processed documents.
- Document processing integration that stores blocks before chunk and citation generation.

## Non-Goals

M6 does not add OCR, VLM parsing, external parser services, GraphRAG extraction, entity/relation extraction, embedding model changes, or frontend UI changes. Chunks and citation units remain the retrieval and grounding units for now; block-to-chunk foreign keys are reserved for a later follow-up.

## Schema

`document_blocks` stores:

- `document_id`
- `block_type`
- `text`
- `source_locator`
- `order_index`
- `heading_level`
- `metadata_json`

Supported block types are `text`, `heading`, `table`, and `code`. `image`, `formula`, and `unknown` are reserved for future parser upgrades.

## Parser Routing

Parser selection goes through `app/services/document_parsing/parser_registry.py`:

- `.txt` -> `TextParser`
- `.md` -> `MarkdownParser`
- `.docx` -> `DocxParser`
- `.pdf` -> `PdfTextParser`

Existing extraction logic is reused for text, DOCX, and PDF paths where appropriate. Markdown gets lightweight structure detection for headings, paragraphs, pipe-style tables, and fenced code blocks.

## Validation

M6 should pass:

```bash
.venv/bin/python -m pytest tests/services/document_parsing
.venv/bin/python -m pytest tests/services/indexing tests/services/retrieval
.venv/bin/python -m pytest tests/test_document_processing.py tests/test_document_indexing.py
.venv/bin/python -m pytest tests/eval/test_rag_eval_metrics.py
make test
make smoke-docx-rag
git diff --check
```

## Future Work

Follow-up milestones can link chunks and citation units back to `document_blocks`, improve table-aware chunking, add GraphRAG extraction from block/chunk/citation-unit sources, and add optional OCR/VLM parser routes without changing the core retrieval interface.
