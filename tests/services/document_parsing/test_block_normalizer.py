from __future__ import annotations

from app.services.document_parsing.block_normalizer import blocks_to_text, normalize_blocks
from app.services.document_parsing.types import DocumentBlock, DocumentBlockType


def test_blocks_to_text_formats_structured_blocks() -> None:
    text = blocks_to_text(
        [
            DocumentBlock(
                block_type=DocumentBlockType.TEXT,
                text="Body",
                order_index=2,
            ),
            DocumentBlock(
                block_type=DocumentBlockType.HEADING,
                text="Title",
                order_index=1,
                heading_level=2,
            ),
            DocumentBlock(
                block_type=DocumentBlockType.TABLE,
                text="| A | B |",
                order_index=3,
            ),
        ]
    )

    assert text == "## Title\n\nBody\n\n[Table]\n| A | B |"


def test_normalize_blocks_drops_empty_text_blocks_and_reindexes() -> None:
    blocks = normalize_blocks(
        [
            DocumentBlock(block_type=DocumentBlockType.TEXT, text="  ", order_index=0),
            DocumentBlock(block_type=DocumentBlockType.TEXT, text=" Body ", order_index=5),
        ]
    )

    assert len(blocks) == 1
    assert blocks[0].text == "Body"
    assert blocks[0].order_index == 0
