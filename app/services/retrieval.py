from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.services.chunk_metadata import (
    build_chunk_snippet,
    infer_source_type_from_filename,
    parse_chunk_metadata,
)
from app.services.document_embedding import (
    DocumentEmbeddingError,
    RetrievedChunk,
    build_text_embedding,
    cosine_similarity,
    search_index,
    tokenize_text,
)
from app.services.reranking import rerank_candidates


HYBRID_VECTOR_WEIGHT = 0.55
HYBRID_LEXICAL_WEIGHT = 0.35
HYBRID_METADATA_WEIGHT = 0.10
INDEXED_DOCUMENT_BONUS = 0.03
DEFAULT_CANDIDATE_MULTIPLIER = 4
MIN_CANDIDATE_LIMIT = 12
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ProcessedRetrievalQuery:
    raw_text: str
    normalized_text: str
    tokens: tuple[str, ...]
    unique_tokens: tuple[str, ...]


@dataclass(slots=True)
class HybridCandidate:
    chunk: RetrievedChunk
    vector_score: float = 0.0
    lexical_score: float = 0.0


def retrieve_chunks_for_documents(
    *,
    db: Session,
    documents: Sequence[Document],
    vector_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    query: str,
    top_k: int,
    required_review_status: DocumentReviewStatus,
    team_id: int | None = None,
) -> list[RetrievedChunk]:
    processed_query = preprocess_retrieval_query(query)
    searchable_documents = [
        item
        for item in documents
        if item.review_status == required_review_status
        and item.processing_status in {
            DocumentProcessingStatus.INDEXED,
            DocumentProcessingStatus.READY,
        }
    ]
    if not searchable_documents:
        return []

    indexed_document_ids = {
        item.id
        for item in searchable_documents
        if item.processing_status == DocumentProcessingStatus.INDEXED
    }
    ready_document_ids = {
        item.id
        for item in searchable_documents
        if item.processing_status == DocumentProcessingStatus.READY
    }
    searchable_document_ids = {item.id for item in searchable_documents}
    document_lookup = {item.id: item for item in documents}
    candidate_limit = max(top_k * DEFAULT_CANDIDATE_MULTIPLIER, MIN_CANDIDATE_LIMIT)

    vector_candidates: list[RetrievedChunk] = []
    if indexed_document_ids:
        try:
            vector_candidates.extend(
                search_index(
                    vector_root=vector_root,
                    scope=scope,
                    knowledge_base_id=knowledge_base_id,
                    query=processed_query.normalized_text,
                    top_k=candidate_limit,
                    team_id=team_id,
                    allowed_document_ids=indexed_document_ids,
                    document_lookup=document_lookup,
                )
            )
        except DocumentEmbeddingError:
            # Keep retrieval usable from database chunks when a precomputed index is unavailable or corrupt.
            pass

    if ready_document_ids:
        vector_candidates.extend(
            search_document_chunks(
                db,
                document_ids=ready_document_ids,
                document_lookup=document_lookup,
                scope=scope,
                knowledge_base_id=knowledge_base_id,
                query=processed_query.normalized_text,
                team_id=team_id,
                limit=candidate_limit,
            )
        )

    lexical_candidates = search_document_chunks_lexical(
        db,
        document_ids=searchable_document_ids,
        document_lookup=document_lookup,
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        processed_query=processed_query,
        team_id=team_id,
        limit=candidate_limit,
    )

    hybrid_results = merge_hybrid_candidates(
        vector_candidates=vector_candidates,
        lexical_candidates=lexical_candidates,
        processed_query=processed_query,
        indexed_document_ids=indexed_document_ids,
        top_k=candidate_limit,
    )
    return rerank_candidates(
        query=processed_query.normalized_text,
        candidates=hybrid_results,
        top_k=top_k,
    )


def preprocess_retrieval_query(query: str) -> ProcessedRetrievalQuery:
    normalized_text = WHITESPACE_PATTERN.sub(" ", query.strip()).lower()
    tokens = tuple(tokenize_text(normalized_text))
    unique_tokens = tuple(dict.fromkeys(tokens))
    return ProcessedRetrievalQuery(
        raw_text=query,
        normalized_text=normalized_text,
        tokens=tokens,
        unique_tokens=unique_tokens,
    )


def search_document_chunks(
    db: Session,
    *,
    document_ids: set[int],
    document_lookup: dict[int, Document],
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    query: str,
    team_id: int | None = None,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    if not document_ids:
        return []

    processed_query = preprocess_retrieval_query(query)
    if not processed_query.tokens:
        return []

    try:
        query_vector = build_text_embedding(processed_query.normalized_text)
    except DocumentEmbeddingError:
        return []

    chunks = _load_document_chunks(db, document_ids=document_ids)
    results: list[RetrievedChunk] = []
    for chunk in chunks:
        try:
            chunk_vector = build_text_embedding(chunk.chunk_text)
        except DocumentEmbeddingError:
            continue

        score = cosine_similarity(query_vector, chunk_vector)
        if score <= 0:
            continue

        results.append(
            _build_retrieved_chunk_from_document_chunk(
                chunk,
                document_lookup=document_lookup,
                scope=scope,
                knowledge_base_id=knowledge_base_id,
                team_id=team_id,
                score=score,
                processed_query=processed_query,
            )
        )

    results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return results[:limit] if limit is not None else results


def search_document_chunks_lexical(
    db: Session,
    *,
    document_ids: set[int],
    document_lookup: dict[int, Document],
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    processed_query: ProcessedRetrievalQuery,
    team_id: int | None = None,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    if not document_ids or not processed_query.tokens:
        return []

    chunks = _load_document_chunks(db, document_ids=document_ids)
    results: list[RetrievedChunk] = []
    for chunk in chunks:
        score = score_lexical_text_match(
            processed_query=processed_query,
            text=chunk.chunk_text,
        )
        if score <= 0:
            continue

        results.append(
            _build_retrieved_chunk_from_document_chunk(
                chunk,
                document_lookup=document_lookup,
                scope=scope,
                knowledge_base_id=knowledge_base_id,
                team_id=team_id,
                score=score,
                processed_query=processed_query,
            )
        )

    results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return results[:limit] if limit is not None else results


def merge_hybrid_candidates(
    *,
    vector_candidates: Sequence[RetrievedChunk],
    lexical_candidates: Sequence[RetrievedChunk],
    processed_query: ProcessedRetrievalQuery,
    indexed_document_ids: set[int],
    top_k: int,
) -> list[RetrievedChunk]:
    candidates: dict[str, HybridCandidate] = {}

    for item in vector_candidates:
        key = _candidate_key(item)
        candidate = candidates.setdefault(key, HybridCandidate(chunk=item))
        if item.score > candidate.vector_score:
            candidate.vector_score = item.score
            candidate.chunk = item

    for item in lexical_candidates:
        key = _candidate_key(item)
        candidate = candidates.setdefault(key, HybridCandidate(chunk=item))
        candidate.lexical_score = max(candidate.lexical_score, item.score)

    if not candidates:
        return []

    max_vector_score = max((item.vector_score for item in candidates.values()), default=0.0)
    max_lexical_score = max((item.lexical_score for item in candidates.values()), default=0.0)

    merged: list[RetrievedChunk] = []
    for candidate in candidates.values():
        vector_score = _normalize_score(candidate.vector_score, max_vector_score)
        lexical_score = _normalize_score(candidate.lexical_score, max_lexical_score)
        metadata_score = score_metadata_match(
            processed_query=processed_query,
            chunk=candidate.chunk,
        )
        indexed_bonus = (
            INDEXED_DOCUMENT_BONUS
            if candidate.chunk.document_id in indexed_document_ids
            else 0.0
        )
        combined_score = min(
            1.0,
            (HYBRID_VECTOR_WEIGHT * vector_score)
            + (HYBRID_LEXICAL_WEIGHT * lexical_score)
            + (HYBRID_METADATA_WEIGHT * metadata_score)
            + indexed_bonus,
        )
        if combined_score <= 0:
            continue

        merged.append(
            replace(
                candidate.chunk,
                score=combined_score,
                snippet=build_query_aware_chunk_snippet(
                    candidate.chunk.text,
                    processed_query=processed_query,
                ),
            )
        )

    merged.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return merged[:top_k]


def score_lexical_text_match(
    *,
    processed_query: ProcessedRetrievalQuery,
    text: str,
) -> float:
    if not processed_query.tokens:
        return 0.0

    chunk_tokens = tuple(tokenize_text(text))
    if not chunk_tokens:
        return 0.0

    query_counts = Counter(processed_query.tokens)
    chunk_counts = Counter(chunk_tokens)
    matched_terms = [
        token
        for token in processed_query.unique_tokens
        if chunk_counts.get(token, 0) > 0
    ]
    if not matched_terms:
        return 0.0

    matched_unique_ratio = len(matched_terms) / len(processed_query.unique_tokens)
    term_frequency_hits = sum(
        min(query_count, chunk_counts.get(token, 0))
        for token, query_count in query_counts.items()
    )
    query_recall = term_frequency_hits / max(sum(query_counts.values()), 1)
    density = term_frequency_hits / max(min(len(chunk_tokens), 300), 1)
    phrase_bonus = (
        0.2
        if processed_query.normalized_text
        and processed_query.normalized_text in WHITESPACE_PATTERN.sub(" ", text.lower())
        else 0.0
    )

    return min(
        1.0,
        (0.55 * matched_unique_ratio)
        + (0.30 * query_recall)
        + (0.15 * min(density * 6, 1.0))
        + phrase_bonus,
    )


def score_metadata_match(
    *,
    processed_query: ProcessedRetrievalQuery,
    chunk: RetrievedChunk,
) -> float:
    if not processed_query.tokens:
        return 0.0

    metadata_text_parts: list[str] = []
    if chunk.section_title:
        metadata_text_parts.append(chunk.section_title)
    if chunk.heading_path:
        metadata_text_parts.extend(chunk.heading_path)
    if chunk.source_locator:
        metadata_text_parts.append(chunk.source_locator)
    if chunk.source_type:
        metadata_text_parts.append(chunk.source_type)
    if chunk.page_number is not None:
        metadata_text_parts.append(f"page {chunk.page_number}")

    metadata_text = " ".join(metadata_text_parts)
    metadata_tokens = set(tokenize_text(metadata_text))
    if not metadata_tokens:
        return 0.0

    query_tokens = set(processed_query.unique_tokens)
    overlap_score = len(query_tokens & metadata_tokens) / max(len(query_tokens), 1)
    title_bonus = 0.0
    if chunk.section_title:
        normalized_title = WHITESPACE_PATTERN.sub(" ", chunk.section_title.strip()).lower()
        if normalized_title and (
            normalized_title in processed_query.normalized_text
            or processed_query.normalized_text in normalized_title
        ):
            title_bonus = 0.25

    page_bonus = 0.0
    if chunk.page_number is not None:
        page_number = str(chunk.page_number)
        if page_number in query_tokens or f"page {page_number}" in processed_query.normalized_text:
            page_bonus = 0.15

    return min(1.0, (0.7 * overlap_score) + title_bonus + page_bonus)


def build_query_aware_chunk_snippet(
    text: str,
    *,
    processed_query: ProcessedRetrievalQuery,
    max_length: int = 260,
) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized

    lower_text = normalized.lower()
    anchor = -1

    if processed_query.normalized_text:
        anchor = lower_text.find(processed_query.normalized_text)

    if anchor < 0:
        for token in processed_query.unique_tokens:
            anchor = lower_text.find(token)
            if anchor >= 0:
                break

    if anchor < 0:
        return build_chunk_snippet(normalized, max_length=max_length)

    preferred_prefix = max_length // 3
    start = max(0, anchor - preferred_prefix)
    end = min(len(normalized), start + max_length)
    if end - start < max_length:
        start = max(0, end - max_length)

    snippet = normalized[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(normalized):
        snippet = snippet.rstrip() + "..."
    return snippet


def _load_document_chunks(db: Session, *, document_ids: set[int]) -> list[DocumentChunk]:
    if not document_ids:
        return []
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id.in_(document_ids))
        .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
    )
    return list(db.scalars(statement))


def _build_retrieved_chunk_from_document_chunk(
    chunk: DocumentChunk,
    *,
    document_lookup: dict[int, Document],
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    team_id: int | None,
    score: float,
    processed_query: ProcessedRetrievalQuery,
) -> RetrievedChunk:
    document = document_lookup.get(chunk.document_id)
    document_name = (
        document.original_filename
        if document is not None
        else f"document_{chunk.document_id}"
    )
    chunk_metadata = parse_chunk_metadata(
        chunk.metadata_json,
        fallback_source_type=infer_source_type_from_filename(document_name),
    )

    return RetrievedChunk(
        chunk_id=chunk.chunk_key,
        document_id=chunk.document_id,
        knowledge_base_id=knowledge_base_id,
        scope=scope.value,
        team_id=team_id,
        document_name=document_name,
        text=chunk.chunk_text,
        snippet=build_query_aware_chunk_snippet(
            chunk.chunk_text,
            processed_query=processed_query,
        ),
        source_type=chunk_metadata.source_type,
        char_start=chunk_metadata.char_start,
        char_end=chunk_metadata.char_end,
        page_number=chunk_metadata.page_number,
        start_time=chunk_metadata.start_time,
        end_time=chunk_metadata.end_time,
        section_title=chunk_metadata.section_title,
        source_locator=chunk_metadata.source_locator,
        heading_path=chunk_metadata.heading_path,
        score=score,
        ocr_provider=chunk_metadata.ocr_provider,
        ocr_provider_version=chunk_metadata.ocr_provider_version,
        asr_provider=chunk_metadata.asr_provider,
        asr_provider_version=chunk_metadata.asr_provider_version,
    )


def _candidate_key(chunk: RetrievedChunk) -> str:
    return f"{chunk.document_id}:{chunk.chunk_id}"


def _normalize_score(value: float, max_value: float) -> float:
    if value <= 0 or max_value <= 0:
        return 0.0
    return min(1.0, value / max_value)
