from __future__ import annotations

from app.services.document_parsing.block_normalizer import blocks_to_plain_text, normalize_blocks
from app.services.document_parsing.types import DocumentBlock, DocumentBlockType, ParsedDocument


def parsed_document_from_extracted_result(
    extracted,
    *,
    parser_name: str,
    filename: str,
) -> ParsedDocument:
    blocks: list[DocumentBlock] = []
    for index, segment in enumerate(extracted.segments):
        metadata = dict(segment.metadata)
        source_locator = _coerce_optional_str(metadata.get("source_locator"))
        block_type = _infer_block_type(segment.text, metadata)
        blocks.append(
            DocumentBlock(
                block_type=block_type,
                text=segment.text,
                source_locator=source_locator,
                order_index=index,
                heading_level=_coerce_optional_int(metadata.get("heading_level")),
                metadata=metadata,
            )
        )
    normalized_blocks = normalize_blocks(blocks)
    return ParsedDocument(
        text=blocks_to_plain_text(normalized_blocks),
        blocks=normalized_blocks,
        metadata={
            "parser": parser_name,
            "source_type": extracted.source_type,
            "extractor": extracted.extractor,
            "encoding": extracted.encoding,
            "page_count": extracted.page_count,
            "original_filename": filename,
        },
    )


def _infer_block_type(text: str, metadata: dict[str, object]) -> DocumentBlockType:
    if metadata.get("block_type") == DocumentBlockType.TABLE.value:
        return DocumentBlockType.TABLE
    if metadata.get("block_type") == DocumentBlockType.CODE.value:
        return DocumentBlockType.CODE
    section_title = metadata.get("section_title")
    if isinstance(section_title, str) and section_title.strip() == text.strip():
        return DocumentBlockType.HEADING
    return DocumentBlockType.TEXT


def _coerce_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _coerce_optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
