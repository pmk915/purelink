from __future__ import annotations

from pathlib import Path

from app.services import document_processing
from app.services.document_parsing.structured_text import (
    parse_structured_text_blocks,
    structured_blocks_to_text,
)
from app.services.document_parsing.types import ParsedDocument


class MarkdownParser:
    parser_name = "markdown"

    def supports(self, *, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() == ".md"

    def parse(
        self,
        file_path: Path,
        *,
        filename: str,
        mime_type: str | None = None,
    ) -> ParsedDocument:
        decoded_text, encoding = document_processing.read_text_file_with_fallback(file_path)
        normalized_blocks = parse_structured_text_blocks(
            decoded_text,
            source_type="markdown",
        )
        return ParsedDocument(
            text=structured_blocks_to_text(normalized_blocks),
            blocks=normalized_blocks,
            metadata={
                "parser": self.parser_name,
                "source_type": "markdown",
                "extractor": "markdown",
                "encoding": encoding,
                "original_filename": filename,
            },
        )
