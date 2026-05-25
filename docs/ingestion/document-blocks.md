# Document Blocks and Parser Routing

M6 introduced structured document blocks.

## Types

`DocumentBlockType` supports:

- `text`
- `heading`
- `table`
- `code`
- `image`
- `formula`
- `unknown`

Core mode actively supports text-like blocks. Image and formula are placeholders for future multimodal parsing.

## Models

- `DocumentBlock`: block type, text, source locator, order index, heading level, metadata.
- `ParsedDocument`: backward-compatible text plus structured block list.

## Persistence

Parsed blocks are stored in `document_blocks`.

## Why It Matters

Blocks preserve document structure before chunking. This helps future chunking, citation precision, table-aware retrieval, lightweight GraphRAG extraction, and optional multimodal parser routing.
