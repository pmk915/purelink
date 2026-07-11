from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChunkingStrategy(StrEnum):
    FIXED = "fixed"
    BLOCK_AWARE = "block_aware"


@dataclass(frozen=True, slots=True)
class ChunkSourceSpan:
    local_start: int
    local_end: int
    source_char_start: int
    source_char_end: int
    page_number: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    section_title: str | None = None
    heading_path: tuple[str, ...] | None = None
    source_locator: str | None = None
    block_type: str | None = None
    line_role: str | None = None
    extractor: str | None = None
    source_type: str | None = None


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    text: str
    metadata: dict[str, object]
    source_spans: tuple[ChunkSourceSpan, ...] = ()
