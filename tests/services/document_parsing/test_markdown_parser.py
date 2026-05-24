from __future__ import annotations

from app.services.document_parsing.parsers.markdown_parser import MarkdownParser
from app.services.document_parsing.types import DocumentBlockType


def test_markdown_parser_preserves_headings_paragraphs_tables_and_code(tmp_path) -> None:
    source = tmp_path / "sample.md"
    source.write_text(
        "# Title\n\n"
        "Paragraph one.\n\n"
        "| A | B |\n"
        "| - | - |\n"
        "| 1 | 2 |\n\n"
        "```python\n"
        "print('hi')\n"
        "```\n",
        encoding="utf-8",
    )

    parsed = MarkdownParser().parse(source, filename="sample.md")

    assert [block.block_type for block in parsed.blocks] == [
        DocumentBlockType.HEADING,
        DocumentBlockType.TEXT,
        DocumentBlockType.TABLE,
        DocumentBlockType.CODE,
    ]
    assert parsed.blocks[0].heading_level == 1
    assert "Title" in parsed.text
    assert "Paragraph one." in parsed.text
    assert "| A | B |" in parsed.text
    assert "print('hi')" in parsed.text
