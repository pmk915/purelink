from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    source_type: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    section_title: str | None = None
    source_locator: str | None = None
    heading_path: tuple[str, ...] | None = None
    ocr_provider: str | None = None
    ocr_provider_version: str | None = None
    ocr_language: str | None = None
    asr_provider: str | None = None
    asr_provider_version: str | None = None
    region_count: int | None = None
    regions: tuple[dict[str, object], ...] | None = None


def infer_source_type_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return "txt"
    if suffix == ".md":
        return "md"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix in {".mp3", ".wav", ".m4a"}:
        return "audio"
    if suffix in {".mp4", ".mov", ".m4v"}:
        return "video"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image"
    return "text"


def build_source_locator(
    *,
    char_start: int | None = None,
    char_end: int | None = None,
    page_number: int | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    section_title: str | None = None,
) -> str | None:
    if page_number is not None:
        return f"page:{page_number}"
    if section_title:
        return f"section:{section_title}"
    if start_time is not None and end_time is not None:
        return f"time:{_format_locator_time(start_time)}-{_format_locator_time(end_time)}"
    if char_start is not None and char_end is not None:
        return f"chars:{char_start}-{char_end}"
    return None


def build_chunk_metadata_payload(
    *,
    source_type: str,
    char_start: int,
    char_end: int,
    page_number: int | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    section_title: str | None = None,
    source_locator: str | None = None,
    heading_path: tuple[str, ...] | list[str] | None = None,
    ocr_provider: str | None = None,
    ocr_provider_version: str | None = None,
    ocr_language: str | None = None,
    asr_provider: str | None = None,
    asr_provider_version: str | None = None,
    region_count: int | None = None,
    regions: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
) -> dict[str, object]:
    normalized_section_title = _normalize_optional_str(section_title)
    normalized_heading_path = _coerce_heading_path(heading_path)
    if normalized_heading_path is None and normalized_section_title:
        normalized_heading_path = (normalized_section_title,)

    locator = _normalize_optional_str(source_locator) or build_source_locator(
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        start_time=start_time,
        end_time=end_time,
        section_title=normalized_section_title,
    )

    payload: dict[str, object] = {
        "source_type": source_type,
        "char_start": char_start,
        "char_end": char_end,
    }
    if page_number is not None:
        payload["page_number"] = page_number
    if start_time is not None:
        payload["start_time"] = round(start_time, 3)
    if end_time is not None:
        payload["end_time"] = round(end_time, 3)
    if normalized_section_title:
        payload["section_title"] = normalized_section_title
    if locator:
        payload["source_locator"] = locator
    if normalized_heading_path:
        payload["heading_path"] = list(normalized_heading_path)
    normalized_ocr_provider = _normalize_optional_str(ocr_provider)
    normalized_ocr_provider_version = _normalize_optional_str(ocr_provider_version)
    normalized_ocr_language = _normalize_optional_str(ocr_language)
    normalized_asr_provider = _normalize_optional_str(asr_provider)
    normalized_asr_provider_version = _normalize_optional_str(asr_provider_version)
    normalized_regions = _coerce_regions(regions)
    if normalized_ocr_provider:
        payload["ocr_provider"] = normalized_ocr_provider
    if normalized_ocr_provider_version:
        payload["ocr_provider_version"] = normalized_ocr_provider_version
    if normalized_ocr_language:
        payload["ocr_language"] = normalized_ocr_language
    if normalized_asr_provider:
        payload["asr_provider"] = normalized_asr_provider
    if normalized_asr_provider_version:
        payload["asr_provider_version"] = normalized_asr_provider_version
    if isinstance(region_count, int) and region_count >= 0:
        payload["region_count"] = region_count
    if normalized_regions:
        payload["regions"] = normalized_regions
    return payload


def parse_chunk_metadata(
    raw_metadata: str | dict[str, object] | None,
    *,
    fallback_source_type: str | None = None,
) -> ChunkMetadata:
    payload: dict[str, object] = {}
    if isinstance(raw_metadata, str):
        try:
            decoded = json.loads(raw_metadata)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            payload = decoded
    elif isinstance(raw_metadata, dict):
        payload = raw_metadata

    source_type = _normalize_optional_str(payload.get("source_type")) or fallback_source_type
    char_start = _coerce_int(payload.get("char_start"))
    char_end = _coerce_int(payload.get("char_end"))
    page_number = _coerce_int(payload.get("page_number"))
    start_time = _coerce_float(payload.get("start_time"))
    end_time = _coerce_float(payload.get("end_time"))
    section_title = _normalize_optional_str(payload.get("section_title"))
    heading_path = _coerce_heading_path(payload.get("heading_path"))
    ocr_provider = _normalize_optional_str(payload.get("ocr_provider"))
    ocr_provider_version = _normalize_optional_str(payload.get("ocr_provider_version"))
    ocr_language = _normalize_optional_str(payload.get("ocr_language"))
    asr_provider = _normalize_optional_str(payload.get("asr_provider"))
    asr_provider_version = _normalize_optional_str(payload.get("asr_provider_version"))
    region_count = _coerce_int(payload.get("region_count"))
    regions = _coerce_regions(payload.get("regions"))
    source_locator = _normalize_optional_str(payload.get("source_locator")) or build_source_locator(
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        start_time=start_time,
        end_time=end_time,
        section_title=section_title,
    )

    return ChunkMetadata(
        source_type=source_type,
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        start_time=start_time,
        end_time=end_time,
        section_title=section_title,
        source_locator=source_locator,
        heading_path=heading_path,
        ocr_provider=ocr_provider,
        ocr_provider_version=ocr_provider_version,
        ocr_language=ocr_language,
        asr_provider=asr_provider,
        asr_provider_version=asr_provider_version,
        region_count=region_count,
        regions=tuple(regions) if regions else None,
    )


def build_chunk_snippet(text: str, *, max_length: int = 260) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


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


def _normalize_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_heading_path(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else None
    if not isinstance(value, list):
        return None

    normalized_items = [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]
    if not normalized_items:
        return None
    return tuple(normalized_items)


def _coerce_regions(
    value: object,
) -> list[dict[str, object]] | None:
    if value is None or not isinstance(value, list):
        return None

    normalized_regions: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized_region: dict[str, object] = {}
        text = _normalize_optional_str(item.get("text"))
        if text:
            normalized_region["text"] = text
        for key in ("left", "top", "width", "height"):
            coordinate = _coerce_int(item.get(key))
            if coordinate is not None:
                normalized_region[key] = coordinate
        confidence = item.get("confidence")
        if isinstance(confidence, (int, float)):
            normalized_region["confidence"] = float(confidence)
        if normalized_region:
            normalized_regions.append(normalized_region)

    return normalized_regions or None


def _format_locator_time(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
