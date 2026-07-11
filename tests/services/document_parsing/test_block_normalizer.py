from __future__ import annotations

from app.services.document_parsing.block_normalizer import (
    assign_block_char_ranges,
    blocks_to_plain_text,
    blocks_to_text,
    normalize_blocks,
)
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


def test_assign_block_char_ranges_match_plain_text_with_repeated_content() -> None:
    blocks = assign_block_char_ranges(
        [
            DocumentBlock(block_type=DocumentBlockType.TEXT, text="Repeated text.", order_index=0),
            DocumentBlock(block_type=DocumentBlockType.TEXT, text="Repeated text.", order_index=1),
            DocumentBlock(block_type=DocumentBlockType.TEXT, text="Unique tail.", order_index=2),
        ]
    )
    plain_text = blocks_to_plain_text(blocks)

    ranges = [
        (block.metadata["char_start"], block.metadata["char_end"])
        for block in blocks
    ]

    assert ranges == [(0, 14), (16, 30), (32, 44)]
    for block in blocks:
        assert plain_text[block.metadata["char_start"]:block.metadata["char_end"]] == block.text
