from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    DocumentIndexStatus,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    ProcessingJobType,
    ProcessingJobStatus,
    ProcessingJobTrigger,
)
from app.schemas.source_locator import (
    PreviewTargetRead,
    SourceLocatorRead,
    normalize_locator_fields,
)


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
    sha256: str | None
    storage_path: str
    review_status: DocumentReviewStatus
    processing_status: DocumentProcessingStatus
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_comment: str | None
    error_message: str | None
    processed_at: datetime | None
    latest_processing_job_id: int | None = None
    latest_processing_job_status: ProcessingJobStatus | None = None
    latest_processing_job_type: ProcessingJobType | None = None
    latest_processing_job_step: str | None = None
    latest_processing_job_error_code: str | None = None
    latest_processing_job_trigger: ProcessingJobTrigger | None = None
    latest_processing_job_attempt_number: int | None = None
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


class DocumentIndexDebugRead(BaseModel):
    status: DocumentIndexStatus | None = None
    provider: str | None = None
    model_name: str | None = None
    model_dim: int | None = None
    model_version: str | None = None
    compatible: bool | None = None
    stale_reason: str | None = None
    error_message: str | None = None


class LatestProcessingJobDebugRead(BaseModel):
    id: int
    status: ProcessingJobStatus
    job_type: ProcessingJobType
    step: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class DocumentRagDebugRead(BaseModel):
    document_id: int
    knowledge_base_id: int
    processing_status: DocumentProcessingStatus
    chunk_count: int
    citation_unit_count: int
    block_count: int
    vector_index: DocumentIndexDebugRead | None = None
    graph_index: DocumentIndexDebugRead | None = None
    latest_processing_job: LatestProcessingJobDebugRead | None = None


class DocumentStatusCheckRead(BaseModel):
    name: str
    label: str
    status: str
    count: int | None = None
    message: str


class DocumentStatusRead(BaseModel):
    document_id: int
    kb_id: int
    filename: str
    processing_status: DocumentProcessingStatus
    rag_ready: bool
    block_count: int
    chunk_count: int
    citation_unit_count: int
    vector_index_status: str
    vector_index_count: int
    vector_index_compatible: bool | None = None
    graph_index_status: str
    entity_count: int
    relation_count: int
    latest_processing_job_step: str | None = None
    latest_processing_job_status: ProcessingJobStatus | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    last_indexed_at: datetime | None = None
    warnings: list[str]
    checks: list[DocumentStatusCheckRead]


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
    mode: str = "chunk_only"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Query cannot be empty.")
        return normalized

    @field_validator("mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        supported = {"auto", "chunk_only", "overview", "graph_vector_mix", "hybrid_text"}
        if normalized not in supported:
            raise ValueError("Unsupported retrieval mode.")
        return normalized


class RetrievedChunkRead(BaseModel):
    chunk_db_id: int | None = None
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    document_name: str
    snippet: str
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
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None
    graph_score: float | None = None
    matched_terms: list[str] | None = None
    candidate_sources: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_source_locator(cls, value: object) -> object:
        return normalize_locator_fields(value)


class RetrievalResponse(BaseModel):
    query: str
    top_k: int
    mode: str | None = None
    requested_mode: str | None = None
    selected_mode: str | None = None
    router_reason: str | None = None
    used_reranker: bool | None = None
    trace_id: int | str | None = None
    results: list[RetrievedChunkRead]


class DocumentPreviewChunkRead(BaseModel):
    chunk_id: str
    chunk_index: int
    text: str
    snippet: str
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


class DocumentPreviewRead(BaseModel):
    document: DocumentRead
    chunks: list[DocumentPreviewChunkRead]
