from __future__ import annotations

import pytest

from app.services.document_parsing.parser_registry import (
    DocumentParserNotFoundError,
    get_parser,
)
from app.services.document_parsing.parsers import (
    DocxParser,
    MarkdownParser,
    PdfTextParser,
    TextParser,
)


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("sample.txt", TextParser),
        ("sample.md", MarkdownParser),
        ("sample.docx", DocxParser),
        ("sample.pdf", PdfTextParser),
    ],
)
def test_parser_registry_selects_parser_by_extension(filename, expected_type) -> None:
    assert isinstance(get_parser(filename=filename), expected_type)


def test_parser_registry_rejects_unsupported_extension() -> None:
    with pytest.raises(DocumentParserNotFoundError, match="Unsupported document parser"):
        get_parser(filename="sample.xlsx")
