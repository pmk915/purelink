from __future__ import annotations

from typing import Any

from app.schemas.source_locator import PreviewTargetRead, SourceLocatorRead


TIMED_SOURCE_TYPES = {"audio", "video"}
TEXT_SOURCE_TYPES = {"text", "markdown", "txt", "md", "docx"}


def build_source_locator_for_chunk(chunk: Any) -> SourceLocatorRead | None:
    source_type = _normalize_optional_str(getattr(chunk, "source_type", None))
    locator_text = _normalize_optional_str(getattr(chunk, "source_locator", None))
    document_id = int(getattr(chunk, "document_id"))
    char_start = _coerce_int(getattr(chunk, "char_start", None))
    char_end = _coerce_int(getattr(chunk, "char_end", None))
    page_number = _coerce_int(getattr(chunk, "page_number", None))
    start_time = _coerce_float(getattr(chunk, "start_time", None))
    end_time = _coerce_float(getattr(chunk, "end_time", None))
    section_title = _normalize_optional_str(getattr(chunk, "section_title", None))
    heading_path = _coerce_heading_path(getattr(chunk, "heading_path", None))
    ocr_provider = _normalize_optional_str(getattr(chunk, "ocr_provider", None))

    if source_type in TIMED_SOURCE_TYPES and start_time is not None and end_time is not None:
        return SourceLocatorRead(
            kind="time_range",
            document_id=document_id,
            source_type=source_type,
            source_locator_text=locator_text,
            start_time=start_time,
            end_time=end_time,
        )

    if source_type == "pdf" and page_number is not None:
        return SourceLocatorRead(
            kind="pdf_page",
            document_id=document_id,
            source_type=source_type,
            source_locator_text=locator_text,
            page_number=page_number,
            char_start=char_start,
            char_end=char_end,
        )

    if source_type == "image":
        return SourceLocatorRead(
            kind="image_region",
            document_id=document_id,
            source_type=source_type,
            source_locator_text=locator_text,
            char_start=char_start,
            char_end=char_end,
            region_hint="ocr_text_region",
            ocr_provider=ocr_provider,
        )

    if (
        source_type in TEXT_SOURCE_TYPES
        or char_start is not None
        or char_end is not None
        or section_title
        or heading_path
    ):
        return SourceLocatorRead(
            kind="text_range",
            document_id=document_id,
            source_type=source_type,
            source_locator_text=locator_text,
            char_start=char_start,
            char_end=char_end,
            section_title=section_title,
            heading_path=heading_path,
        )

    if locator_text:
        return SourceLocatorRead(
            kind="unknown",
            document_id=document_id,
            source_type=source_type,
            source_locator_text=locator_text,
        )

    return None


def build_preview_target_for_chunk(chunk: Any) -> PreviewTargetRead | None:
    locator = build_source_locator_for_chunk(chunk)
    if locator is None:
        return None

    return PreviewTargetRead(
        document_id=locator.document_id,
        source_type=locator.source_type,
        locator_kind=locator.kind,
        source_locator_text=locator.source_locator_text,
        char_start=locator.char_start,
        char_end=locator.char_end,
        section_title=locator.section_title,
        page_number=locator.page_number,
        start_time=locator.start_time,
        end_time=locator.end_time,
    )


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_heading_path(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else None
    if not isinstance(value, (list, tuple)):
        return None

    normalized_items = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    return normalized_items or None
