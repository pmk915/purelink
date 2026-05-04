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

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question cannot be empty.")
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
    heading_path: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_source_locator(cls, value: object) -> object:
        return normalize_locator_fields(value)


class QuestionAnswerResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: list[CitationRead]
