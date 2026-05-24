from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import RetrievalFilteredReason


class RetrievalTraceCandidate(BaseModel):
    document_id: int | None = None
    chunk_id: int | None = None
    citation_unit_id: int | None = None

    document_name: str | None = None
    source_locator: str | None = None
    candidate_text_preview: str | None = None

    vector_score: float | None = None
    keyword_score: float | None = None
    graph_score: float | None = None
    rerank_score: float | None = None
    final_score: float | None = None

    initial_rank: int | None = None
    rerank_rank: int | None = None
    final_rank: int | None = None

    selected_for_context: bool = False
    filtered_reason: RetrievalFilteredReason = RetrievalFilteredReason.UNKNOWN

    index_status: str | None = None
    index_provider: str | None = None
    index_model_name: str | None = None
    index_model_dim: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "RetrievalFilteredReason",
    "RetrievalTraceCandidate",
]
