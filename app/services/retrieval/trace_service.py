from __future__ import annotations

from datetime import UTC, datetime
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem
from app.services.retrieval.trace_types import RetrievalTraceCandidate


logger = logging.getLogger("purelink.retrieval.trace")

DEFAULT_PREVIEW_MAX_CHARS = 400


def start_retrieval_trace(
    db: Session,
    *,
    user_id: int | None,
    knowledge_base_id: int | None,
    conversation_id: int | None = None,
    message_id: int | None = None,
    query: str,
    mode: str,
    top_k: int | None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    reranker_enabled: bool = False,
    reranker_provider: str | None = None,
    reranker_model: str | None = None,
) -> RetrievalTrace:
    trace = RetrievalTrace(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        conversation_id=conversation_id,
        message_id=message_id,
        query=query,
        mode=mode,
        top_k=top_k,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        reranker_enabled=reranker_enabled,
        reranker_provider=reranker_provider,
        reranker_model=reranker_model,
    )
    db.add(trace)
    db.flush()
    return trace


def finish_retrieval_trace(
    db: Session,
    *,
    trace_id: int,
    initial_candidate_count: int,
    final_evidence_count: int,
    used_reranker: bool,
    metadata: dict[str, object] | None = None,
) -> None:
    trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == trace_id))
    if trace is None:
        return

    completed_at = datetime.now(UTC)
    trace.initial_candidate_count = initial_candidate_count
    trace.final_evidence_count = final_evidence_count
    trace.used_reranker = used_reranker
    trace.completed_at = completed_at
    if trace.created_at is not None:
        trace.duration_ms = int((completed_at - _as_aware_utc(trace.created_at)).total_seconds() * 1000)
    trace.metadata_json = _dump_metadata(metadata)
    db.flush()


def merge_retrieval_trace_metadata(
    db: Session,
    *,
    trace_id: int,
    metadata: dict[str, object],
) -> None:
    trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == trace_id))
    if trace is None:
        return

    existing: dict[str, object] = {}
    if trace.metadata_json:
        try:
            payload = json.loads(trace.metadata_json)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            existing = payload
    trace.metadata_json = _dump_metadata({**existing, **metadata})
    db.flush()


def record_retrieval_trace_items(
    db: Session,
    *,
    trace_id: int,
    candidates: list[RetrievalTraceCandidate],
    preview_max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
) -> None:
    if not candidates:
        return

    items = [
        RetrievalTraceItem(
            trace_id=trace_id,
            document_id=candidate.document_id,
            chunk_id=candidate.chunk_id,
            citation_unit_id=candidate.citation_unit_id,
            document_name=candidate.document_name,
            source_locator=candidate.source_locator,
            candidate_text_preview=truncate_candidate_preview(
                candidate.candidate_text_preview,
                max_chars=preview_max_chars,
            ),
            vector_score=candidate.vector_score,
            keyword_score=candidate.keyword_score,
            graph_score=candidate.graph_score,
            rerank_score=candidate.rerank_score,
            final_score=candidate.final_score,
            initial_rank=candidate.initial_rank,
            rerank_rank=candidate.rerank_rank,
            final_rank=candidate.final_rank,
            selected_for_context=candidate.selected_for_context,
            filtered_reason=candidate.filtered_reason,
            index_status=candidate.index_status,
            index_provider=candidate.index_provider,
            index_model_name=candidate.index_model_name,
            index_model_dim=candidate.index_model_dim,
            metadata_json=_dump_metadata(candidate.metadata),
        )
        for candidate in candidates
    ]
    db.add_all(items)
    db.flush()


def truncate_candidate_preview(
    value: str | None,
    *,
    max_chars: int = DEFAULT_PREVIEW_MAX_CHARS,
) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max(0, max_chars - 3)].rstrip() + "..."


def _dump_metadata(metadata: dict[str, object] | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "DEFAULT_PREVIEW_MAX_CHARS",
    "finish_retrieval_trace",
    "record_retrieval_trace_items",
    "start_retrieval_trace",
    "truncate_candidate_preview",
]
