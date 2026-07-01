from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetrievalMode(str, Enum):
    AUTO = "auto"
    CHUNK_ONLY = "chunk_only"
    OVERVIEW = "overview"
    HYBRID_TEXT = "hybrid_text"
    GRAPH_LOCAL = "graph_local"
    GRAPH_GLOBAL = "graph_global"
    GRAPH_VECTOR_MIX = "graph_vector_mix"


class RetrievedEvidence(BaseModel):
    document_id: int
    chunk_id: str | int
    citation_unit_id: int | None = None
    citation_id: int | None = None
    chunk_db_id: int | None = None

    text: str
    source_locator: str | None = None

    knowledge_base_id: int | None = None
    scope: str | None = None
    team_id: int | None = None
    document_name: str | None = None
    snippet: str | None = None
    source_type: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    section_title: str | None = None
    heading_path: list[str] | None = None

    vector_score: float | None = None
    keyword_score: float | None = None
    graph_score: float | None = None
    rerank_score: float | None = None
    final_score: float | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    query: str = Field(min_length=1)
    knowledge_base_id: int = Field(ge=1)
    user_id: int = Field(ge=1)

    mode: RetrievalMode = RetrievalMode.CHUNK_ONLY
    top_k: int = Field(default=8, ge=1, le=50)

    filters: dict[str, Any] = Field(default_factory=dict)
    include_citations: bool = True

    team_id: int | None = None
    scope: Any | None = None
    conversation_id: int | None = None
    message_id: int | None = None
    enable_trace: bool = True

    db: Any | None = Field(default=None, exclude=True)
    documents: Sequence[Any] = Field(default_factory=list, exclude=True)
    vector_root: Path | None = Field(default=None, exclude=True)
    required_review_status: Any | None = Field(default=None, exclude=True)
    settings: Any | None = Field(default=None, exclude=True)
    evidence_query: str | None = None

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Retrieval query cannot be empty.")
        return normalized

    @field_validator("evidence_query")
    @classmethod
    def normalize_evidence_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RetrievalResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    query: str
    mode: RetrievalMode
    requested_mode: RetrievalMode | None = None
    selected_mode: RetrievalMode | None = None
    router_reason: str | None = None

    evidences: list[RetrievedEvidence]
    context_text: str

    used_reranker: bool = False
    trace_id: int | str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
