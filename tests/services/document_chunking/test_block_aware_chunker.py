from __future__ import annotations

from app.models.enums import DocumentBlockType
from app.services.document_chunking.block_aware_chunker import build_block_aware_chunks
from app.services.document_parsing.types import DocumentBlock


def _block(
    block_type: DocumentBlockType,
    text: str,
    order_index: int,
    *,
    heading_level: int | None = None,
    source_locator: str | None = None,
    metadata: dict[str, object] | None = None,
) -> DocumentBlock:
    return DocumentBlock(
        block_type=block_type,
        text=text,
        order_index=order_index,
        heading_level=heading_level,
        source_locator=source_locator,
        metadata=metadata or {},
    )


def _chunk(blocks: list[DocumentBlock], **overrides):
    options = {
        "source_type": "markdown",
        "target_chars": 120,
        "max_chars": 180,
        "min_chars": 20,
        "table_max_chars": 240,
        "overlap_chars": 20,
    }
    options.update(overrides)
    return build_block_aware_chunks(blocks, **options)


def test_heading_and_paragraphs_produce_section_chunk_with_heading_path() -> None:
    chunks = _chunk(
        [
            _block(DocumentBlockType.HEADING, "Retrieval Layer", 0, heading_level=1),
            _block(DocumentBlockType.TEXT, "RetrievalRequest carries query context.", 1),
            _block(DocumentBlockType.TEXT, "RetrievedEvidence keeps source grounding.", 2),
        ]
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["chunk_strategy"] == "block_aware"
    assert chunks[0].metadata["heading_path"] == ["Retrieval Layer"]
    assert chunks[0].metadata["section_title"] == "Retrieval Layer"
    assert "RetrievalRequest" in chunks[0].text


def test_top_level_headings_are_not_merged_across_sections() -> None:
    chunks = _chunk(
        [
            _block(DocumentBlockType.HEADING, "M1", 0, heading_level=1),
            _block(DocumentBlockType.TEXT, "Retrieval layer content.", 1),
            _block(DocumentBlockType.HEADING, "M2", 2, heading_level=1),
            _block(DocumentBlockType.TEXT, "Provider layer content.", 3),
        ],
        min_chars=80,
    )

    assert [item.metadata["heading_path"] for item in chunks] == [["M1"], ["M2"]]


def test_small_table_block_is_preserved_as_one_chunk() -> None:
    table = "| Role | Action |\n| --- | --- |\n| Admin | Delete document |"
    chunks = _chunk(
        [
            _block(DocumentBlockType.HEADING, "Permissions", 0, heading_level=1),
            _block(DocumentBlockType.TABLE, table, 1),
        ],
        table_max_chars=200,
    )

    assert len(chunks) == 1
    assert chunks[0].text == table
    assert chunks[0].metadata["block_types"] == ["table"]
    assert chunks[0].metadata["heading_path"] == ["Permissions"]


def test_large_table_splits_by_rows() -> None:
    table = "\n".join(f"| row {index} | value {index} |" for index in range(20))
    chunks = _chunk(
        [_block(DocumentBlockType.TABLE, table, 0)],
        table_max_chars=80,
    )

    assert len(chunks) > 1
    assert all(len(item.text) <= 80 for item in chunks)
    assert all(item.metadata["block_types"] == ["table"] for item in chunks)


def test_code_block_becomes_standalone_chunk() -> None:
    chunks = _chunk(
        [
            _block(DocumentBlockType.TEXT, "Intro paragraph.", 0),
            _block(DocumentBlockType.CODE, "def retrieve():\n    return []", 1),
            _block(DocumentBlockType.TEXT, "Outro paragraph.", 2),
        ]
    )

    assert len(chunks) == 3
    assert chunks[1].metadata["block_types"] == ["code"]
    assert "def retrieve" in chunks[1].text


def test_oversized_text_section_falls_back_to_boundary_split() -> None:
    text = "\n\n".join(f"Paragraph {index} contains retrieval details." for index in range(10))
    chunks = _chunk(
        [
            _block(DocumentBlockType.HEADING, "Long Section", 0, heading_level=1),
            _block(DocumentBlockType.TEXT, text, 1),
        ],
        max_chars=120,
    )

    assert len(chunks) > 1
    assert all(item.metadata["heading_path"] == ["Long Section"] for item in chunks)
    assert all(item.metadata["chunk_strategy"] == "block_aware" for item in chunks)


def test_missing_blocks_return_empty_for_fixed_fallback_caller() -> None:
    assert _chunk([]) == []


def test_block_aware_chunks_include_source_spans_and_single_page_metadata() -> None:
    chunks = _chunk(
        [
            _block(
                DocumentBlockType.TEXT,
                "PDF page one identity text.",
                0,
                source_locator="page:1",
                metadata={
                    "char_start": 0,
                    "char_end": 27,
                    "page_number": 1,
                    "extractor": "pymupdf",
                },
            ),
            _block(
                DocumentBlockType.TEXT,
                "PDF page one relationship text.",
                1,
                source_locator="page:1",
                metadata={
                    "char_start": 29,
                    "char_end": 60,
                    "page_number": 1,
                    "extractor": "pymupdf",
                },
            ),
        ],
        source_type="pdf",
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["page_number"] == 1
    assert chunks[0].metadata["extractor"] == "pymupdf"
    assert [(span.local_start, span.local_end) for span in chunks[0].source_spans] == [
        (0, 27),
        (29, 60),
    ]
    assert [(span.source_char_start, span.source_char_end) for span in chunks[0].source_spans] == [
        (0, 27),
        (29, 60),
    ]
    assert all(span.page_number == 1 for span in chunks[0].source_spans)


def test_large_block_split_source_spans_keep_original_offsets() -> None:
    text = "\n".join(f"Line {index} keeps source offsets." for index in range(8))
    chunks = _chunk(
        [
            _block(
                DocumentBlockType.TEXT,
                text,
                0,
                metadata={"char_start": 100, "char_end": 100 + len(text)},
            ),
        ],
        max_chars=70,
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.source_spans) == 1
        span = chunk.source_spans[0]
        assert chunk.text == text[span.source_char_start - 100:span.source_char_end - 100]
        assert span.local_start == 0
        assert span.local_end == len(chunk.text)
