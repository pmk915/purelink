from __future__ import annotations

from pathlib import Path

from app.services import document_processing
from app.services.document_parsing.parsers._extracted_adapter import (
    parsed_document_from_extracted_result,
)
from app.services.document_parsing.types import ParsedDocument


class DocxParser:
    parser_name = "minimal_docx_text"

    def supports(self, *, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() == ".docx"

    def parse(
        self,
        file_path: Path,
        *,
        filename: str,
        mime_type: str | None = None,
    ) -> ParsedDocument:
        extracted = document_processing.extract_text_from_docx(source_path=file_path)
        return parsed_document_from_extracted_result(
            extracted,
            parser_name=self.parser_name,
            filename=filename,
        )
