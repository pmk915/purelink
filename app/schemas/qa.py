from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.source_locator import (
    PreviewTargetRead,
    SourceLocatorRead,
    normalize_locator_fields,
)


class QuestionAnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_id: int | None = Field(default=None, ge=1)
    mode: str = "auto"

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question cannot be empty.")
        return normalized

    @field_validator("mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        supported = {"auto", "chunk_only", "overview", "graph_vector_mix", "hybrid_text"}
        if normalized not in supported:
            raise ValueError("Unsupported retrieval mode.")
        return normalized


class CitationRead(BaseModel):
    citation_id: int | None = None
    citation_marker: str | None = None
    citation_unit_id: int | None = None
    chunk_db_id: int | None = None
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    document_name: str | None = None
    snippet: str | None = None
    text: str
    source_type: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    section_title: str | None = None
    source_locator: SourceLocatorRead | None = None
    preview_target: PreviewTargetRead | None = None
    heading_path: list[str] = Field(default_factory=list)
    citation_ready: bool = False
    retrieval_mode: str | None = None
    score: float | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_source_locator(cls, value: object) -> object:
        normalized = normalize_locator_fields(value)
        if not isinstance(normalized, dict):
            return normalized

        payload = dict(normalized)
        payload["heading_path"] = _normalize_heading_path(payload.get("heading_path"))
        payload["char_start"], payload["char_end"] = _normalize_char_range(
            payload.get("char_start"),
            payload.get("char_end"),
        )
        payload["source_locator"] = _normalize_nested_locator(
            payload.get("source_locator"),
            normalize_heading=True,
        )
        payload["preview_target"] = _normalize_nested_locator(
            payload.get("preview_target"),
            normalize_heading=False,
        )
        if "citation_ready" not in payload:
            payload["citation_ready"] = (
                payload.get("citation_unit_id") is not None
                and payload.get("source_locator") is not None
            )
        return payload


def _normalize_heading_path(value: object) -> list[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_char_range(start: object, end: object) -> tuple[int | None, int | None]:
    if (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start < end
    ):
        return start, end
    return None, None


def _normalize_nested_locator(
    value: object,
    *,
    normalize_heading: bool,
) -> object:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    normalized["char_start"], normalized["char_end"] = _normalize_char_range(
        normalized.get("char_start"),
        normalized.get("char_end"),
    )
    if normalize_heading:
        normalized["heading_path"] = _normalize_heading_path(
            normalized.get("heading_path")
        )
    return normalized


class QuestionAnswerResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: list[CitationRead]
    intent: str | None = None
    retrieval_mode: str | None = None
    requested_mode: str | None = None
    selected_mode: str | None = None
    router_reason: str | None = None
    used_reranker: bool | None = None
    trace_id: int | str | None = None
