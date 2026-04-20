from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    owner_id: int
    submitted_by: int
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    storage_path: str
    review_status: DocumentReviewStatus
    processing_status: DocumentProcessingStatus
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_comment: str | None
    created_at: datetime
    updated_at: datetime


class DocumentRejectRequest(BaseModel):
    review_comment: str = Field(min_length=1, max_length=2000)

    @field_validator("review_comment")
    @classmethod
    def normalize_review_comment(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Review comment cannot be empty.")
        return normalized


class DocumentParseRead(BaseModel):
    document_id: int
    knowledge_base_id: int
    processing_status: DocumentProcessingStatus
    parsed_path: str
    parser: str
    extracted_char_count: int


class DocumentChunkRead(BaseModel):
    document_id: int
    knowledge_base_id: int
    processing_status: DocumentProcessingStatus
    chunked_path: str
    source_parsed_path: str
    chunk_count: int
    chunk_size: int


class DocumentEmbedRead(BaseModel):
    document_id: int
    knowledge_base_id: int
    processing_status: DocumentProcessingStatus
    index_path: str
    embedded_chunk_count: int
    embedding_dimension: int


class RetrievalQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Query cannot be empty.")
        return normalized


class RetrievedChunkRead(BaseModel):
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    text: str
    score: float


class RetrievalResponse(BaseModel):
    query: str
    top_k: int
    results: list[RetrievedChunkRead]
