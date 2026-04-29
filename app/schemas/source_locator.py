from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


SourceLocatorKind = Literal[
    "text_range",
    "pdf_page",
    "image_region",
    "time_range",
    "unknown",
]
TEXT_SOURCE_TYPES = {"text", "markdown", "txt", "md", "docx"}


class SourceLocatorRead(BaseModel):
    kind: SourceLocatorKind
    document_id: int
    source_type: str | None = None
    source_locator_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    section_title: str | None = None
    heading_path: list[str] | None = None
    page_number: int | None = None
    page_region: dict[str, object] | None = None
    bbox: dict[str, object] | None = None
    region_hint: str | None = None
    ocr_provider: str | None = None
    start_time: float | None = None
    end_time: float | None = None


class PreviewTargetRead(BaseModel):
    kind: Literal["document_preview"] = "document_preview"
    document_id: int
    source_type: str | None = None
    locator_kind: SourceLocatorKind
    source_locator_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    section_title: str | None = None
    page_number: int | None = None
    start_time: float | None = None
    end_time: float | None = None


def normalize_locator_fields(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload

    source_locator = payload.get("source_locator")
    if not isinstance(source_locator, str):
        return payload

    locator = build_locator_from_payload(
        payload,
        source_locator_text=source_locator,
    )
    normalized = dict(payload)
    normalized["source_locator"] = locator.model_dump()
    if normalized.get("preview_target") is None:
        normalized["preview_target"] = build_preview_target_from_locator(locator).model_dump()
    return normalized


def build_locator_from_payload(
    payload: dict[str, object],
    *,
    source_locator_text: str | None = None,
) -> SourceLocatorRead:
    document_id = _coerce_int(payload.get("document_id")) or 0
    source_type = _normalize_optional_str(payload.get("source_type"))
    char_start = _coerce_int(payload.get("char_start"))
    char_end = _coerce_int(payload.get("char_end"))
    page_number = _coerce_int(payload.get("page_number"))
    start_time = _coerce_float(payload.get("start_time"))
    end_time = _coerce_float(payload.get("end_time"))
    section_title = _normalize_optional_str(payload.get("section_title"))
    heading_path = _coerce_heading_path(payload.get("heading_path"))

    kind: SourceLocatorKind = "unknown"
    if source_type in {"audio", "video"} and start_time is not None and end_time is not None:
        kind = "time_range"
    elif source_type == "pdf" and page_number is not None:
        kind = "pdf_page"
    elif source_type == "image":
        kind = "image_region"
    elif (
        source_type in TEXT_SOURCE_TYPES
        or char_start is not None
        or char_end is not None
        or section_title
        or heading_path
    ):
        kind = "text_range"

    return SourceLocatorRead(
        kind=kind,
        document_id=document_id,
        source_type=source_type,
        source_locator_text=source_locator_text,
        char_start=char_start,
        char_end=char_end,
        section_title=section_title,
        heading_path=heading_path,
        page_number=page_number,
        region_hint="ocr_text_region" if kind == "image_region" else None,
        ocr_provider=_normalize_optional_str(payload.get("ocr_provider")),
        start_time=start_time,
        end_time=end_time,
    )


def build_preview_target_from_locator(locator: SourceLocatorRead) -> PreviewTargetRead:
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
    if not isinstance(value, list):
        return None

    normalized_items = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    return normalized_items or None
