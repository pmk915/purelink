from __future__ import annotations

from types import SimpleNamespace

from app.services.source_locator import (
    build_preview_target_for_chunk,
    build_source_locator_for_chunk,
)
from app.schemas.qa import CitationRead


def _chunk(**overrides):
    defaults = {
        "document_id": 7,
        "source_type": "text",
        "source_locator": "text:chunk:0",
        "char_start": 10,
        "char_end": 40,
        "page_number": None,
        "start_time": None,
        "end_time": None,
        "section_title": None,
        "heading_path": None,
        "ocr_provider": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_text_locator_uses_text_range_with_section_context() -> None:
    locator = build_source_locator_for_chunk(
        _chunk(
            source_type="markdown",
            source_locator="heading:Architecture",
            section_title="Architecture",
            heading_path=("Architecture",),
        )
    )

    assert locator is not None
    assert locator.kind == "text_range"
    assert locator.source_locator_text == "heading:Architecture"
    assert locator.section_title == "Architecture"
    assert locator.heading_path == ["Architecture"]


def test_pdf_locator_uses_page_number_and_preview_target() -> None:
    chunk = _chunk(
        source_type="pdf",
        source_locator="page:3",
        page_number=3,
    )

    locator = build_source_locator_for_chunk(chunk)
    preview_target = build_preview_target_for_chunk(chunk)

    assert locator is not None
    assert locator.kind == "pdf_page"
    assert locator.page_number == 3
    assert preview_target is not None
    assert preview_target.locator_kind == "pdf_page"
    assert preview_target.page_number == 3


def test_citation_schema_coerces_legacy_string_locator() -> None:
    citation = CitationRead.model_validate(
        {
            "chunk_id": "7:0",
            "document_id": 7,
            "knowledge_base_id": 3,
            "scope": "personal",
            "team_id": None,
            "document_name": "manual.pdf",
            "snippet": "Page citation text",
            "text": "Page citation text",
            "source_type": "pdf",
            "char_start": 0,
            "char_end": 18,
            "page_number": 2,
            "start_time": None,
            "end_time": None,
            "section_title": None,
            "source_locator": "page:2",
            "heading_path": None,
        }
    )

    assert citation.source_locator is not None
    assert citation.source_locator.kind == "pdf_page"
    assert citation.source_locator.source_locator_text == "page:2"
    assert citation.preview_target is not None
    assert citation.preview_target.locator_kind == "pdf_page"
