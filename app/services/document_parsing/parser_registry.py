from __future__ import annotations

from pathlib import Path

from app.services.document_parsing.types import DocumentParser


class DocumentParserNotFoundError(ValueError):
    pass


def default_parsers() -> list[DocumentParser]:
    from app.services.document_parsing.parsers.docx_parser import DocxParser
    from app.services.document_parsing.parsers.markdown_parser import MarkdownParser
    from app.services.document_parsing.parsers.pdf_text_parser import PdfTextParser
    from app.services.document_parsing.parsers.text_parser import TextParser

    return [
        TextParser(),
        MarkdownParser(),
        DocxParser(),
        PdfTextParser(),
    ]


def get_parser(
    *,
    filename: str,
    mime_type: str | None = None,
    parsers: list[DocumentParser] | None = None,
) -> DocumentParser:
    active_parsers = parsers or default_parsers()
    for parser in active_parsers:
        if parser.supports(filename=filename, mime_type=mime_type):
            return parser
    suffix = Path(filename).suffix.lower() or filename
    raise DocumentParserNotFoundError(f"Unsupported document parser for file type: {suffix}.")
