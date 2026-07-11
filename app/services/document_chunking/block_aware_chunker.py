from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from app.models.enums import DocumentBlockType
from app.services.document_chunking.types import ChunkDraft, ChunkSourceSpan

PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n")


@dataclass(frozen=True, slots=True)
class _TextPiece:
    text: str
    start: int
    end: int

    def __len__(self) -> int:
        return len(self.text)


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
    heading_stack: list[tuple[int, str]] = []
    section_blocks: list[object] = []

    def flush_section() -> None:
        nonlocal section_blocks
        if not section_blocks:
            return
        chunks.extend(
            _chunk_section_blocks(
                section_blocks,
                heading_path=[text for _, text in heading_stack],
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
            _update_heading_stack(heading_stack, _block_text(block), _heading_level(block))
            continue
        if block_type == DocumentBlockType.TABLE:
            flush_section()
            chunks.extend(
                _chunk_standalone_block(
                    block,
                    heading_path=[text for _, text in heading_stack],
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
                    heading_path=[text for _, text in heading_stack],
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
            current_draft = _build_chunk(
                current,
                heading_path=heading_path,
                source_type=source_type,
            )
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
            span_offset = len(previous.text) + 2
            chunks.append(
                ChunkDraft(
                    text=merged_text,
                    metadata=merged_metadata,
                    source_spans=(
                        *previous.source_spans,
                        *_offset_source_spans(current_draft.source_spans, offset=span_offset),
                    ),
                )
            )
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
        chunks.append(
            ChunkDraft(
                text=piece.text,
                metadata=metadata,
                source_spans=_build_source_spans(
                    [block],
                    chunk_text=piece.text,
                    source_type=source_type,
                    single_block_slice=(piece.start, piece.end),
                ),
            )
        )
    return chunks


def _split_text_by_boundaries(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[_TextPiece]:
    line_pieces = _line_pieces(text)
    if len(line_pieces) > 1:
        pieces = _pack_units(line_pieces, max_chars=max_chars)
        if all(len(piece) <= max_chars for piece in pieces):
            return pieces

    paragraphs = _paragraph_pieces(text)
    if len(paragraphs) > 1:
        pieces = _pack_units(paragraphs, max_chars=max_chars)
        if all(len(piece) <= max_chars for piece in pieces):
            return pieces

    pieces: list[_TextPiece] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        piece = _trim_piece(text, start, end)
        if piece is not None:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return pieces


def _pack_units(units: list[_TextPiece], *, max_chars: int) -> list[_TextPiece]:
    pieces: list[_TextPiece] = []
    current: list[_TextPiece] = []
    current_length = 0
    for unit in units:
        if len(unit) > max_chars:
            if current:
                pieces.append(_merge_pieces(current))
                current = []
                current_length = 0
            nested_pieces = _split_text_by_boundaries(
                unit.text,
                max_chars=max_chars,
                overlap_chars=0,
            )
            pieces.extend(_offset_pieces(nested_pieces, offset=unit.start))
            continue
        separator_length = 0 if not current else 1
        if current and current_length + separator_length + len(unit) > max_chars:
            pieces.append(_merge_pieces(current))
            current = [unit]
            current_length = len(unit)
            continue
        current.append(unit)
        current_length += separator_length + len(unit)
    if current:
        pieces.append(_merge_pieces(current))
    return pieces


def _build_chunk(
    blocks: list[object],
    *,
    heading_path: list[str],
    source_type: str,
) -> ChunkDraft:
    text = _join_block_text(blocks)
    return ChunkDraft(
        text=text,
        metadata=_build_metadata(blocks, heading_path=heading_path, source_type=source_type),
        source_spans=_build_source_spans(blocks, chunk_text=text, source_type=source_type),
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
    _copy_single_value_metadata(metadata, blocks, "page_number")
    _copy_single_value_metadata(metadata, blocks, "extractor")
    _copy_single_value_metadata(metadata, blocks, "line_role")
    return metadata


def _update_heading_stack(
    heading_stack: list[tuple[int, str]],
    heading: str,
    heading_level: int | None,
) -> None:
    level = max(1, min(int(heading_level or 1), 6))
    while heading_stack and heading_stack[-1][0] >= level:
        heading_stack.pop()
    heading_stack.append((level, heading))


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


def _build_source_spans(
    blocks: list[object],
    *,
    chunk_text: str,
    source_type: str,
    single_block_slice: tuple[int, int] | None = None,
) -> tuple[ChunkSourceSpan, ...]:
    spans: list[ChunkSourceSpan] = []
    local_cursor = 0
    if single_block_slice is not None and len(blocks) == 1:
        block = blocks[0]
        start, end = single_block_slice
        metadata = _block_metadata(block)
        source_start = _metadata_int(metadata, "char_start")
        if source_start is None:
            return ()
        spans.append(
            _source_span_from_block(
                block,
                local_start=0,
                local_end=len(chunk_text),
                source_char_start=source_start + start,
                source_char_end=source_start + end,
                source_type=source_type,
            )
        )
        return tuple(spans)

    for index, block in enumerate(blocks):
        text = _block_text(block)
        if not text:
            continue
        if index > 0:
            local_cursor += 2
        metadata = _block_metadata(block)
        source_start = _metadata_int(metadata, "char_start")
        source_end = _metadata_int(metadata, "char_end")
        if source_start is not None and source_end is not None:
            spans.append(
                _source_span_from_block(
                    block,
                    local_start=local_cursor,
                    local_end=local_cursor + len(text),
                    source_char_start=source_start,
                    source_char_end=source_end,
                    source_type=source_type,
                )
            )
        local_cursor += len(text)
    return tuple(spans)


def _source_span_from_block(
    block: object,
    *,
    local_start: int,
    local_end: int,
    source_char_start: int,
    source_char_end: int,
    source_type: str,
) -> ChunkSourceSpan:
    metadata = _block_metadata(block)
    heading_path = _coerce_heading_path(metadata.get("heading_path"))
    return ChunkSourceSpan(
        local_start=local_start,
        local_end=local_end,
        source_char_start=source_char_start,
        source_char_end=source_char_end,
        page_number=_metadata_int(metadata, "page_number"),
        start_time=_metadata_float(metadata, "start_time"),
        end_time=_metadata_float(metadata, "end_time"),
        section_title=_metadata_str(metadata, "section_title"),
        heading_path=heading_path,
        source_locator=_source_locator(block) or _metadata_str(metadata, "source_locator"),
        block_type=_block_type(block).value,
        line_role=_metadata_str(metadata, "line_role"),
        extractor=_metadata_str(metadata, "extractor"),
        source_type=source_type,
    )


def _block_metadata(block: object) -> dict[str, object]:
    raw_metadata = getattr(block, "metadata_json", None)
    if raw_metadata is None:
        raw_metadata = getattr(block, "metadata", None)
    return coerce_block_metadata(raw_metadata)


def _metadata_int(metadata: dict[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _metadata_float(metadata: dict[str, object], key: str) -> float | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_heading_path(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    items = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return items or None


def _copy_single_value_metadata(
    metadata: dict[str, object],
    blocks: list[object],
    key: str,
) -> None:
    values = {
        value
        for block in blocks
        for value in [_block_metadata(block).get(key)]
        if value is not None
    }
    if len(values) == 1:
        metadata[key] = values.pop()


def _line_pieces(text: str) -> list[_TextPiece]:
    pieces: list[_TextPiece] = []
    start = 0
    for line in text.splitlines(keepends=True):
        end = start + len(line)
        piece = _trim_piece(text, start, end)
        if piece is not None:
            pieces.append(piece)
        start = end
    return pieces


def _paragraph_pieces(text: str) -> list[_TextPiece]:
    pieces: list[_TextPiece] = []
    start = 0
    for match in PARAGRAPH_BOUNDARY.finditer(text):
        piece = _trim_piece(text, start, match.start())
        if piece is not None:
            pieces.append(piece)
        start = match.end()
    piece = _trim_piece(text, start, len(text))
    if piece is not None:
        pieces.append(piece)
    return pieces


def _trim_piece(text: str, start: int, end: int) -> _TextPiece | None:
    trimmed_start = start
    trimmed_end = end
    while trimmed_start < trimmed_end and text[trimmed_start].isspace():
        trimmed_start += 1
    while trimmed_end > trimmed_start and text[trimmed_end - 1].isspace():
        trimmed_end -= 1
    if trimmed_start >= trimmed_end:
        return None
    return _TextPiece(
        text=text[trimmed_start:trimmed_end],
        start=trimmed_start,
        end=trimmed_end,
    )


def _merge_pieces(pieces: list[_TextPiece]) -> _TextPiece:
    return _TextPiece(
        text="\n".join(piece.text for piece in pieces),
        start=pieces[0].start,
        end=pieces[-1].end,
    )


def _offset_pieces(pieces: list[_TextPiece], *, offset: int) -> list[_TextPiece]:
    return [
        _TextPiece(text=piece.text, start=piece.start + offset, end=piece.end + offset)
        for piece in pieces
    ]


def _offset_source_spans(
    source_spans: tuple[ChunkSourceSpan, ...],
    *,
    offset: int,
) -> tuple[ChunkSourceSpan, ...]:
    return tuple(
        ChunkSourceSpan(
            local_start=span.local_start + offset,
            local_end=span.local_end + offset,
            source_char_start=span.source_char_start,
            source_char_end=span.source_char_end,
            page_number=span.page_number,
            start_time=span.start_time,
            end_time=span.end_time,
            section_title=span.section_title,
            heading_path=span.heading_path,
            source_locator=span.source_locator,
            block_type=span.block_type,
            line_role=span.line_role,
            extractor=span.extractor,
            source_type=span.source_type,
        )
        for span in source_spans
    )


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
