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

## Block-aware Chunking

M14 adds optional block-aware chunking with:

```env
CHUNK_STRATEGY=block_aware
```

When enabled, PureLink uses `document_blocks` to build section-aware chunks:

- headings update `heading_path`
- text blocks under a heading are grouped into section chunks
- small table blocks stay together
- large tables split by rows/lines
- code blocks are standalone chunks
- oversized sections fall back to boundary-based splitting

If blocks are missing or invalid, document processing falls back to the default `fixed` strategy instead of failing.

The default remains:

```env
CHUNK_STRATEGY=fixed
```

## Why It Matters

Blocks preserve document structure before chunking. This helps future chunking, citation precision, table-aware retrieval, lightweight GraphRAG extraction, and optional multimodal parser routing.
