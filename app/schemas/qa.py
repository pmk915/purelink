from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    text: str


class QuestionAnswerResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: list[CitationRead]
