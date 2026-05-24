from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.models.enums import DocumentBlockType


class DocumentBlock(BaseModel):
    block_type: DocumentBlockType
    text: str = ""
    source_locator: str | None = None
    order_index: int
    heading_level: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    text: str
    blocks: list[DocumentBlock]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentParser(Protocol):
    parser_name: str

    def supports(self, *, filename: str, mime_type: str | None = None) -> bool:
        ...

    def parse(
        self,
        file_path: Path,
        *,
        filename: str,
        mime_type: str | None = None,
    ) -> ParsedDocument:
        ...
