from __future__ import annotations

import json
import re
from typing import Any

from app.models.enums import DocumentBlockType
from app.services.document_chunking.types import ChunkDraft

PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")


def build_block_aware_chunks(
    blocks: list[object],
    *,
    source_type: str,
    target_chars: int,
    max_chars: int,
    min_chars: int,
    table_max_chars: int,
    overlap_chars: int,
) -> list[ChunkDraft]:
    ordered_blocks = [
        block
        for block in sorted(blocks, key=lambda item: int(getattr(item, "order_index", 0) or 0))
        if _block_text(block)
    ]
    if not ordered_blocks:
        return []

    chunks: list[ChunkDraft] = []
    heading_path: list[str] = []
    section_blocks: list[object] = []

    def flush_section() -> None:
        nonlocal section_blocks
        if not section_blocks:
            return
        chunks.extend(
            _chunk_section_blocks(
                section_blocks,
                heading_path=heading_path,
                source_type=source_type,
                target_chars=target_chars,
                max_chars=max_chars,
                min_chars=min_chars,
                overlap_chars=overlap_chars,
            )
        )
        section_blocks = []

    for block in ordered_blocks:
        block_type = _block_type(block)
        if block_type == DocumentBlockType.HEADING:
            flush_section()
            _update_heading_path(heading_path, _block_text(block), _heading_level(block))
            continue
        if block_type == DocumentBlockType.TABLE:
            flush_section()
            chunks.extend(
                _chunk_standalone_block(
                    block,
                    heading_path=heading_path,
                    source_type=source_type,
                    max_chars=table_max_chars,
                    overlap_chars=0,
                )
            )
            continue
        if block_type == DocumentBlockType.CODE:
            flush_section()
            chunks.extend(
                _chunk_standalone_block(
                    block,
                    heading_path=heading_path,
                    source_type=source_type,
                    max_chars=max_chars,
                    overlap_chars=0,
                )
            )
            continue
        section_blocks.append(block)

    flush_section()
    return chunks


def _chunk_section_blocks(
    blocks: list[object],
    *,
    heading_path: list[str],
    source_type: str,
    target_chars: int,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    current: list[object] = []
    current_length = 0

    for block in blocks:
        text = _block_text(block)
        if len(text) > max_chars:
            if current:
                chunks.append(
                    _build_chunk(current, heading_path=heading_path, source_type=source_type)
                )
                current = []
                current_length = 0
            chunks.extend(
                _split_large_block(
                    block,
                    heading_path=heading_path,
                    source_type=source_type,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )
            continue

        separator_length = 0 if not current else 2
        if current and current_length + separator_length + len(text) > target_chars:
            chunks.append(_build_chunk(current, heading_path=heading_path, source_type=source_type))
            current = [block]
            current_length = len(text)
            continue

        current.append(block)
        current_length += separator_length + len(text)

    if current:
        if (
            chunks
            and current_length < min_chars
            and _same_parent_heading(chunks[-1].metadata.get("heading_path"), heading_path)
        ):
            previous = chunks.pop()
            merged_text = f"{previous.text}\n\n{_join_block_text(current)}"
            merged_metadata = dict(previous.metadata)
            merged_metadata["block_types"] = _merge_unique(
                previous.metadata.get("block_types"),
                [_block_type(block).value for block in current],
            )
            merged_metadata["source_block_ids"] = _merge_unique(
                previous.metadata.get("source_block_ids"),
                _block_ids(current),
            )
            merged_metadata["source_block_order_indexes"] = _merge_unique(
                previous.metadata.get("source_block_order_indexes"),
                _block_order_indexes(current),
            )
            chunks.append(ChunkDraft(text=merged_text, metadata=merged_metadata))
        else:
            chunks.append(_build_chunk(current, heading_path=heading_path, source_type=source_type))
    return chunks


def _chunk_standalone_block(
    block: object,
    *,
    heading_path: list[str],
    source_type: str,
    max_chars: int,
    overlap_chars: int,
) -> list[ChunkDraft]:
    text = _block_text(block)
    if len(text) <= max_chars:
        return [_build_chunk([block], heading_path=heading_path, source_type=source_type)]
    return _split_large_block(
        block,
        heading_path=heading_path,
        source_type=source_type,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )


def _split_large_block(
    block: object,
    *,
    heading_path: list[str],
    source_type: str,
    max_chars: int,
    overlap_chars: int,
) -> list[ChunkDraft]:
    text = _block_text(block)
    pieces = _split_text_by_boundaries(text, max_chars=max_chars, overlap_chars=overlap_chars)
    chunks: list[ChunkDraft] = []
    for index, piece in enumerate(pieces):
        metadata = _build_metadata([block], heading_path=heading_path, source_type=source_type)
        metadata["split_part"] = index
        metadata["split_part_count"] = len(pieces)
        chunks.append(ChunkDraft(text=piece, metadata=metadata))
    return chunks


def _split_text_by_boundaries(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines()]
    if len(lines) > 1:
        pieces = _pack_units([line for line in lines if line.strip()], max_chars=max_chars)
        if all(len(piece) <= max_chars for piece in pieces):
            return pieces

    paragraphs = [item.strip() for item in PARAGRAPH_BOUNDARY.split(text) if item.strip()]
    if len(paragraphs) > 1:
        pieces = _pack_units(paragraphs, max_chars=max_chars)
        if all(len(piece) <= max_chars for piece in pieces):
            return pieces

    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return pieces


def _pack_units(units: list[str], *, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    current_length = 0
    for unit in units:
        if len(unit) > max_chars:
            if current:
                pieces.append("\n".join(current))
                current = []
                current_length = 0
            pieces.extend(_split_text_by_boundaries(unit, max_chars=max_chars, overlap_chars=0))
            continue
        separator_length = 0 if not current else 1
        if current and current_length + separator_length + len(unit) > max_chars:
            pieces.append("\n".join(current))
            current = [unit]
            current_length = len(unit)
            continue
        current.append(unit)
        current_length += separator_length + len(unit)
    if current:
        pieces.append("\n".join(current))
    return pieces


def _build_chunk(
    blocks: list[object],
    *,
    heading_path: list[str],
    source_type: str,
) -> ChunkDraft:
    return ChunkDraft(
        text=_join_block_text(blocks),
        metadata=_build_metadata(blocks, heading_path=heading_path, source_type=source_type),
    )


def _build_metadata(
    blocks: list[object],
    *,
    heading_path: list[str],
    source_type: str,
) -> dict[str, object]:
    source_locators = [
        locator
        for locator in (_source_locator(block) for block in blocks)
        if locator
    ]
    block_types = [_block_type(block).value for block in blocks]
    metadata: dict[str, object] = {
        "source_type": source_type,
        "chunk_strategy": "block_aware",
        "block_types": _unique(block_types),
        "source_block_order_indexes": _block_order_indexes(blocks),
    }
    block_ids = _block_ids(blocks)
    if block_ids:
        metadata["source_block_ids"] = block_ids
    if heading_path:
        metadata["heading_path"] = list(heading_path)
        metadata["section_title"] = heading_path[-1]
    if source_locators:
        metadata["source_locator"] = source_locators[0]
        metadata["source_locators"] = _unique(source_locators)
    return metadata


def _update_heading_path(heading_path: list[str], heading: str, heading_level: int | None) -> None:
    level = max(1, min(int(heading_level or 1), 6))
    del heading_path[level - 1:]
    heading_path.append(heading)


def _same_parent_heading(left: object, right: list[str]) -> bool:
    if not isinstance(left, list) or not all(isinstance(item, str) for item in left):
        return False
    return left[:-1] == right[:-1]


def _join_block_text(blocks: list[object]) -> str:
    return "\n\n".join(_block_text(block) for block in blocks if _block_text(block)).strip()


def _block_text(block: object) -> str:
    return str(getattr(block, "text", "") or "").strip()


def _block_type(block: object) -> DocumentBlockType:
    raw_type = getattr(block, "block_type", DocumentBlockType.UNKNOWN)
    if isinstance(raw_type, DocumentBlockType):
        return raw_type
    try:
        return DocumentBlockType(str(raw_type))
    except ValueError:
        return DocumentBlockType.UNKNOWN


def _heading_level(block: object) -> int | None:
    value = getattr(block, "heading_level", None)
    return int(value) if isinstance(value, int) else None


def _source_locator(block: object) -> str | None:
    value = getattr(block, "source_locator", None)
    return str(value).strip() if value else None


def _block_ids(blocks: list[object]) -> list[int]:
    return [
        int(block_id)
        for block_id in (getattr(block, "id", None) for block in blocks)
        if isinstance(block_id, int)
    ]


def _block_order_indexes(blocks: list[object]) -> list[int]:
    return [
        int(order_index)
        for order_index in (getattr(block, "order_index", None) for block in blocks)
        if isinstance(order_index, int)
    ]


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _merge_unique(existing: object, values: list[Any]) -> list[Any]:
    initial = existing if isinstance(existing, list) else []
    return _unique([*initial, *values])


def coerce_block_metadata(raw_metadata: str | dict[str, object] | None) -> dict[str, object]:
    if isinstance(raw_metadata, dict):
        return raw_metadata
    if not raw_metadata:
        return {}
    try:
        decoded = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}
