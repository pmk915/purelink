from __future__ import annotations

from app.services.document_parsing.types import DocumentBlock, DocumentBlockType


def blocks_to_text(blocks: list[DocumentBlock]) -> str:
    parts: list[str] = []
    for block in sorted(blocks, key=lambda item: item.order_index):
        text = block.text.strip()
        if not text:
            continue
        if block.block_type == DocumentBlockType.HEADING:
            level = block.heading_level or 1
            parts.append(f"{'#' * max(1, min(level, 6))} {text}")
            continue
        if block.block_type == DocumentBlockType.TABLE:
            parts.append(text if text.startswith("[Table]") else f"[Table]\n{text}")
            continue
        if block.block_type == DocumentBlockType.CODE:
            language = block.metadata.get("language")
            fence = f"```{language}" if isinstance(language, str) and language else "```"
            parts.append(f"{fence}\n{text}\n```")
            continue
        parts.append(text)
    return "\n\n".join(parts)


def blocks_to_plain_text(blocks: list[DocumentBlock]) -> str:
    return "\n\n".join(
        block.text.strip()
        for block in sorted(blocks, key=lambda item: item.order_index)
        if block.text.strip()
    )


def normalize_blocks(blocks: list[DocumentBlock]) -> list[DocumentBlock]:
    normalized: list[DocumentBlock] = []
    for block in sorted(blocks, key=lambda item: item.order_index):
        text = block.text.strip()
        if not text and block.block_type not in {DocumentBlockType.IMAGE, DocumentBlockType.FORMULA}:
            continue
        normalized.append(
            block.model_copy(
                update={
                    "text": text,
                    "order_index": len(normalized),
                }
            )
        )
    return normalized
