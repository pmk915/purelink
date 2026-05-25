from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
import logging
import zlib

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.services.document_embedding import RetrievedChunk
from app.services.retrieval import chunk_retriever
from app.services.retrieval.keyword_retriever import retrieve_keyword_chunks


logger = logging.getLogger("purelink.retrieval")


@dataclass(frozen=True, slots=True)
class HybridTextRetrievalMetadata:
    keyword_candidate_count: int
    keyword_failed: bool = False
    fallback_reason: str | None = None


@dataclass(slots=True)
class _HybridCandidate:
    chunk: RetrievedChunk
    vector_score: float | None = None
    keyword_score: float | None = None
    matched_terms: tuple[str, ...] = ()
    candidate_sources: tuple[str, ...] = ()


def retrieve_hybrid_text_chunks(
    *,
    db: Session,
    documents: Sequence[Document],
    vector_root,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    query: str,
    top_k: int,
    required_review_status: DocumentReviewStatus,
    team_id: int | None = None,
    keyword_documents: Sequence[Document] | None = None,
) -> tuple[list[RetrievedChunk], HybridTextRetrievalMetadata]:
    vector_candidates = chunk_retriever.retrieve_chunks_for_documents(
        db=db,
        documents=documents,
        vector_root=vector_root,
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        query=query,
        top_k=top_k,
        required_review_status=required_review_status,
        team_id=team_id,
    )

    keyword_candidates: list[RetrievedChunk] = []
    fallback_reason = None
    keyword_failed = False
    try:
        keyword_candidates = retrieve_keyword_chunks(
            db=db,
            documents=keyword_documents or documents,
            scope=scope,
            knowledge_base_id=knowledge_base_id,
            query=query,
            required_review_status=required_review_status,
            team_id=team_id,
        )
    except Exception as exc:
        keyword_failed = True
        fallback_reason = f"{type(exc).__name__}: {exc}"
        logger.warning("keyword retrieval failed; falling back to vector candidates", exc_info=True)

    merged = merge_hybrid_text_candidates(
        vector_candidates=vector_candidates,
        keyword_candidates=keyword_candidates,
        top_k=top_k,
    )
    return merged, HybridTextRetrievalMetadata(
        keyword_candidate_count=len(keyword_candidates),
        keyword_failed=keyword_failed,
        fallback_reason=fallback_reason,
    )


def merge_hybrid_text_candidates(
    *,
    vector_candidates: Sequence[RetrievedChunk],
    keyword_candidates: Sequence[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    candidates: dict[tuple[object, ...], _HybridCandidate] = {}

    for item in vector_candidates:
        key = _candidate_key(item)
        candidate = candidates.setdefault(key, _HybridCandidate(chunk=item))
        score = item.vector_score if item.vector_score is not None else item.score
        if candidate.vector_score is None or score > candidate.vector_score:
            candidate.vector_score = score
            candidate.chunk = item
        candidate.candidate_sources = _merge_sources(candidate.candidate_sources, item.candidate_sources or ("vector",))

    for item in keyword_candidates:
        key = _candidate_key(item)
        candidate = candidates.setdefault(key, _HybridCandidate(chunk=item))
        score = item.keyword_score if item.keyword_score is not None else item.score
        if candidate.keyword_score is None or score > candidate.keyword_score:
            candidate.keyword_score = score
        candidate.matched_terms = _merge_terms(candidate.matched_terms, item.matched_terms)
        candidate.candidate_sources = _merge_sources(candidate.candidate_sources, item.candidate_sources or ("keyword",))

    if not candidates:
        return []

    max_vector_score = max((item.vector_score or 0.0 for item in candidates.values()), default=0.0)
    max_keyword_score = max((item.keyword_score or 0.0 for item in candidates.values()), default=0.0)

    merged: list[RetrievedChunk] = []
    for candidate in candidates.values():
        vector_score = candidate.vector_score
        keyword_score = candidate.keyword_score
        vector_norm = _normalize(vector_score, max_vector_score)
        keyword_norm = _normalize(keyword_score, max_keyword_score)
        if vector_score is not None and keyword_score is not None:
            combined_score = (0.7 * vector_norm) + (0.3 * keyword_norm)
        elif keyword_score is not None:
            combined_score = keyword_score
        else:
            combined_score = vector_score or candidate.chunk.score
        merged.append(
            replace(
                candidate.chunk,
                score=combined_score,
                vector_score=vector_score,
                keyword_score=keyword_score,
                matched_terms=candidate.matched_terms or candidate.chunk.matched_terms,
                candidate_sources=_merge_sources(candidate.candidate_sources, ()),
            )
        )

    merged.sort(key=lambda item: (-item.score, item.document_id, str(item.chunk_id)))
    return merged[:top_k]


def _candidate_key(chunk: RetrievedChunk) -> tuple[object, ...]:
    if chunk.chunk_db_id is not None:
        return ("chunk_db", chunk.chunk_db_id)
    if chunk.chunk_id:
        return ("chunk", chunk.document_id, str(chunk.chunk_id))
    preview_hash = zlib.adler32((chunk.snippet or chunk.text[:300]).encode("utf-8"))
    return ("text", chunk.document_id, chunk.source_locator, preview_hash)


def _normalize(value: float | None, max_value: float) -> float:
    if value is None or value <= 0 or max_value <= 0:
        return 0.0
    return min(1.0, value / max_value)


def _merge_sources(existing: tuple[str, ...], incoming: tuple[str, ...]) -> tuple[str, ...]:
    merged = list(existing)
    for source in incoming:
        if source and source not in merged:
            merged.append(source)
    return tuple(merged)


def _merge_terms(
    existing: tuple[str, ...],
    incoming: tuple[str, ...] | None,
) -> tuple[str, ...]:
    merged = list(existing)
    for term in incoming or ():
        if term and term not in merged:
            merged.append(term)
    return tuple(merged)
