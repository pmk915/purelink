from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChunkingStrategy(StrEnum):
    FIXED = "fixed"
    BLOCK_AWARE = "block_aware"


@dataclass(frozen=True, slots=True)
class ChunkDraft:
    text: str
    metadata: dict[str, object]
