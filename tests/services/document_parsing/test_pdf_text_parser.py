from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from app.core.config import get_settings
from app.models.enums import DocumentBlockType
from app.services.document_parsing.parsers.pdf_text_parser import PdfTextParser
from app.services.document_processing import (
    DocumentProcessingError,
    ExtractedTextSegment,
    RenderedPDFPage,
    build_extracted_text_result,
)
from app.services.ocr_provider import OCRProviderError, OCRRegion, OCRResult


def _write_pdf(path: Path, pages: list[list[tuple[int, str]]]) -> None:
    with fitz.open() as document:
        for entries in pages:
            page = document.new_page()
            for y, text in entries:
                page.insert_text((72, y), text)
        document.save(path)


def test_one_page_pdf_preserves_text_and_page_provenance(tmp_path: Path) -> None:
    source = tmp_path / "manual.pdf"
    text = "RETRIEVAL_MIN_SCORE=0.15 uses graph_vector_mix and __init__."
    _write_pdf(source, [[(72, text)]])

    parsed = PdfTextParser().parse(source, filename=source.name)

    assert parsed.text == text
    assert parsed.metadata["page_count"] == 1
    assert parsed.metadata["extractor"] == "pymupdf"
    assert len(parsed.blocks) == 1
    block = parsed.blocks[0]
    assert block.block_type == DocumentBlockType.TEXT
    assert block.order_index == 0
    assert block.source_locator == "page:1"
    assert block.metadata["source_type"] == "pdf"
    assert block.metadata["page_number"] == 1
    assert block.metadata["extractor"] == "pymupdf"


def test_pdf_blocks_are_sorted_and_keep_valid_json_bboxes(tmp_path: Path) -> None:
    source = tmp_path / "ordered.pdf"
    # Write lower text first: extraction must use supported geometric sorting.
    _write_pdf(source, [[(160, "Lower block stays searchable."), (72, "Upper block stays searchable.")]])

    parser = PdfTextParser()
    parsed = parser.parse(source, filename=source.name)

    assert [block.text for block in parsed.blocks] == [
        "Upper block stays searchable.",
        "Lower block stays searchable.",
    ]
    assert [block.order_index for block in parsed.blocks] == [0, 1]
    assert all(block.source_locator == "page:1" for block in parsed.blocks)
    for block in parsed.blocks:
        bbox = block.metadata["bbox"]
        assert isinstance(bbox, list) and len(bbox) == 4
        assert all(isinstance(value, float) and math.isfinite(value) for value in bbox)
        x0, y0, x1, y1 = bbox
        assert 0 <= x0 < x1 <= 595
        assert 0 <= y0 < y1 <= 842
    assert parsed.blocks[0].metadata["bbox"][1] < parsed.blocks[1].metadata["bbox"][1]
    serialized = parsed.model_dump(mode="json")
    assert json.loads(json.dumps(serialized, allow_nan=False)) == serialized
    assert parser.parse(source, filename=source.name).model_dump() == parsed.model_dump()


def test_pdf_physical_pages_include_empty_pages_without_empty_blocks(tmp_path: Path) -> None:
    source = tmp_path / "pages.pdf"
    _write_pdf(source, [[(72, "First physical page text.")], [], [(72, "Third physical page text.")]])

    parsed = PdfTextParser().parse(source, filename=source.name)

    assert parsed.metadata["page_count"] == 3
    assert [block.text for block in parsed.blocks] == [
        "First physical page text.",
        "Third physical page text.",
    ]
    assert [block.metadata["page_number"] for block in parsed.blocks] == [1, 3]
    assert [block.source_locator for block in parsed.blocks] == ["page:1", "page:3"]
    assert [block.order_index for block in parsed.blocks] == [0, 1]


def test_pdf_image_descriptions_are_not_text_blocks(tmp_path: Path) -> None:
    source = tmp_path / "illustrated.pdf"
    with fitz.open() as document:
        page = document.new_page()
        image = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
        image.clear_with(255)
        page.insert_image(fitz.Rect(72, 120, 120, 168), stream=image.tobytes("png"))
        page.insert_text((72, 72), "Native text remains available beside an image.")
        document.save(source)

    parsed = PdfTextParser().parse(source, filename=source.name)

    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].text == "Native text remains available beside an image."


@pytest.mark.parametrize("content", [b"not a PDF", b"%PDF-1.4\nbroken document"])
def test_invalid_pdf_keeps_extraction_failure_code(tmp_path: Path, content: bytes) -> None:
    source = tmp_path / "invalid.pdf"
    source.write_bytes(content)

    with pytest.raises(DocumentProcessingError) as error:
        PdfTextParser().parse(source, filename=source.name)

    assert error.value.error_code == "PDF_TEXT_EXTRACTION_FAILED"


@pytest.mark.parametrize("enable_ocr", [False, True])
def test_pdf_empty_native_text_preserves_optional_ocr_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    enable_ocr: bool,
) -> None:
    source = tmp_path / "empty-native.pdf"
    _write_pdf(source, [[]])
    monkeypatch.setenv("ENABLE_OCR", str(enable_ocr).lower())
    get_settings.cache_clear()
    calls = []

    def fake_scanned_pdf(*, source_path: Path, direct_error_code: str):
        calls.append((source_path, direct_error_code))
        return build_extracted_text_result(
            source_type="pdf",
            extractor="ocr_pdf:test",
            page_count=1,
            raw_segments=[ExtractedTextSegment(
                text="Optional OCR recovered readable text.",
                metadata={"source_type": "pdf", "page_number": 1, "source_locator": "page:1"},
            )],
        )

    monkeypatch.setattr("app.services.document_processing.extract_text_from_scanned_pdf", fake_scanned_pdf)
    if enable_ocr:
        parsed = PdfTextParser().parse(source, filename=source.name)
        assert parsed.metadata["extractor"] == "ocr_pdf:test"
        assert parsed.blocks[0].source_locator == "page:1"
        assert calls == [(source, "PDF_TEXT_EXTRACTION_FAILED")]
    else:
        with pytest.raises(DocumentProcessingError, match="OCR is not enabled") as error:
            PdfTextParser().parse(source, filename=source.name)
        assert error.value.error_code == "PDF_TEXT_EXTRACTION_FAILED"
        assert calls == []


@pytest.mark.parametrize("outcome", ["valid", "unavailable", "empty"])
def test_pdf_ocr_fallback_keeps_provider_results_and_error_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    source = tmp_path / "ocr-fallback.pdf"
    _write_pdf(source, [[]])
    monkeypatch.setenv("ENABLE_OCR", "true")
    get_settings.cache_clear()
    image_path = tmp_path / "rendered.png"
    monkeypatch.setattr(
        "app.services.document_processing.render_pdf_pages_to_images",
        lambda source_path, output_dir: [RenderedPDFPage(page_number=1, image_path=image_path)],
    )
    text = "Optional OCR keeps PDF page provenance." if outcome == "valid" else ""

    def fake_provider():
        if outcome == "unavailable":
            raise OCRProviderError("Test provider unavailable.")
        result = OCRResult(
            text=text,
            provider_name="test",
            provider_version="1",
            language="eng",
            regions=(OCRRegion(text=text, left=10, top=20, width=100, height=30),) if text else (),
        )
        return SimpleNamespace(extract_text=lambda path: result)

    monkeypatch.setattr("app.services.document_processing.resolve_ocr_provider", fake_provider)
    if outcome == "valid":
        parsed = PdfTextParser().parse(source, filename=source.name)
        assert parsed.text == text
        assert parsed.metadata["extractor"] == "ocr_pdf:test"
        assert parsed.blocks[0].source_locator == "page:1"
        assert parsed.blocks[0].metadata["ocr_provider"] == "test"
        assert parsed.blocks[0].metadata["region"] == {
            "left": 10, "top": 20, "width": 100, "height": 30,
        }
    else:
        with pytest.raises(DocumentProcessingError) as error:
            PdfTextParser().parse(source, filename=source.name)
        assert error.value.error_code == (
            "OCR_PROVIDER_UNAVAILABLE" if outcome == "unavailable" else "OCR_NO_TEXT_FOUND"
        )
