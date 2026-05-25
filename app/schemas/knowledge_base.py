from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import KnowledgeBaseScope
from app.schemas.processing_job import ProcessingJobSubmissionRead


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Knowledge base name cannot be empty.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None


class KnowledgeBaseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("Knowledge base name cannot be empty.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None


class TeamKnowledgeBaseCreateRequest(KnowledgeBaseCreateRequest):
    pass


class TeamKnowledgeBaseUpdateRequest(KnowledgeBaseUpdateRequest):
    pass


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    scope: KnowledgeBaseScope
    owner_id: int | None
    team_id: int | None
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseReindexRead(BaseModel):
    knowledge_base_id: int
    queued_jobs: list[ProcessingJobSubmissionRead]
    queued_document_ids: list[int]
    skipped_document_ids: list[int]


class KnowledgeBaseRagHealthRead(BaseModel):
    document_count: int
    document_status_counts: dict[str, int]
    index_status_counts: dict[str, dict[str, int]]
