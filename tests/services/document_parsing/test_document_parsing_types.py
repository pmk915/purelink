from __future__ import annotations

from app.services.document_parsing.types import DocumentBlock, DocumentBlockType, ParsedDocument


def test_document_block_type_values_exist() -> None:
    assert DocumentBlockType.TEXT.value == "text"
    assert DocumentBlockType.HEADING.value == "heading"
    assert DocumentBlockType.TABLE.value == "table"
    assert DocumentBlockType.CODE.value == "code"
    assert DocumentBlockType.IMAGE.value == "image"
    assert DocumentBlockType.FORMULA.value == "formula"


def test_parsed_document_keeps_text_and_blocks() -> None:
    parsed = ParsedDocument(
        text="Title\n\nBody",
        blocks=[
            DocumentBlock(
                block_type=DocumentBlockType.HEADING,
                text="Title",
                order_index=0,
                heading_level=1,
            ),
            DocumentBlock(
                block_type=DocumentBlockType.TEXT,
                text="Body",
                order_index=1,
            ),
        ],
    )

    assert parsed.text == "Title\n\nBody"
    assert [block.order_index for block in parsed.blocks] == [0, 1]
