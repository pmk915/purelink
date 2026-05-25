from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.services.document_embedding import RetrievedChunk
from app.services.retrieval.chunk_retriever import (
    _build_retrieved_chunk_from_document_chunk,
    preprocess_retrieval_query,
)


TECH_TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_{}.-]+)+|"
    r"/[A-Za-z0-9_{}./:-]+|"
    r"\b[A-Z][A-Z0-9_]{2,}\b|"
    r"\b\d{8}_\d{3,6}\b|"
    r"\b[A-Za-z0-9_][A-Za-z0-9_.-]*\b|"
    r"[\u4e00-\u9fff]+"
)
WHITESPACE_PATTERN = re.compile(r"\s+")
PATH_SPLIT_PATTERN = re.compile(r"[/\\]")
TECH_SPLIT_PATTERN = re.compile(r"[-./:_]")


@dataclass(frozen=True, slots=True)
class KeywordMatch:
    score: float
    matched_terms: tuple[str, ...]


def normalize_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text.strip().lower())


def extract_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for match in TECH_TOKEN_PATTERN.finditer(query):
        token = match.group(0).strip()
        if not token:
            continue
        terms.extend(_expand_token(token))

    normalized_terms = [normalize_text(term) for term in terms if term.strip()]
    return list(dict.fromkeys(term for term in normalized_terms if term))


def score_keyword_match(
    *,
    query: str,
    query_terms: Sequence[str],
    chunk_text: str,
    document_name: str | None = None,
    metadata_text: str | None = None,
) -> KeywordMatch:
    if not query_terms:
        return KeywordMatch(score=0.0, matched_terms=())

    normalized_query = normalize_text(query)
    normalized_chunk = normalize_text(chunk_text)
    normalized_document_name = normalize_text(document_name or "")
    normalized_metadata = normalize_text(metadata_text or "")
    searchable_text = " ".join(
        part
        for part in (normalized_chunk, normalized_document_name, normalized_metadata)
        if part
    )
    if not searchable_text:
        return KeywordMatch(score=0.0, matched_terms=())

    matched_terms = tuple(term for term in query_terms if term in searchable_text)
    if not matched_terms:
        return KeywordMatch(score=0.0, matched_terms=())

    matched_ratio = len(matched_terms) / max(len(query_terms), 1)
    phrase_bonus = 0.25 if normalized_query and normalized_query in searchable_text else 0.0
    document_name_bonus = (
        0.2
        if normalized_document_name
        and any(term in normalized_document_name for term in matched_terms)
        else 0.0
    )
    technical_bonus = min(
        0.25,
        0.05
        * sum(
            1
            for term in matched_terms
            if any(separator in term for separator in ("_", "-", "/", ".", "{", "}"))
            or any(char.isdigit() for char in term)
        ),
    )
    score = min(1.5, matched_ratio + phrase_bonus + document_name_bonus + technical_bonus)
    return KeywordMatch(score=score, matched_terms=matched_terms)


def retrieve_keyword_chunks(
    *,
    db: Session,
    documents: Sequence[Document],
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    query: str,
    required_review_status: DocumentReviewStatus,
    team_id: int | None = None,
    top_n: int | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    settings = get_settings()
    effective_top_n = top_n or settings.keyword_retrieval_top_n
    effective_min_score = min_score if min_score is not None else settings.keyword_retrieval_min_score
    query_terms = extract_query_terms(query)
    if not query_terms:
        return []

    searchable_documents = [
        item
        for item in documents
        if item.review_status == required_review_status
        and item.processing_status == DocumentProcessingStatus.INDEXED
    ]
    if not searchable_documents:
        return []

    document_lookup = {item.id: item for item in searchable_documents}
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id.in_(set(document_lookup)))
        .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
    )

    processed_query = preprocess_retrieval_query(query)
    candidates: list[RetrievedChunk] = []
    for chunk in db.scalars(statement):
        document = document_lookup.get(chunk.document_id)
        document_name = document.original_filename if document is not None else None
        metadata_text = _metadata_text(chunk)
        match = score_keyword_match(
            query=query,
            query_terms=query_terms,
            chunk_text=chunk.chunk_text,
            document_name=document_name,
            metadata_text=metadata_text,
        )
        if match.score < effective_min_score:
            continue

        base_chunk = _build_retrieved_chunk_from_document_chunk(
            chunk,
            document_lookup=document_lookup,
            scope=scope,
            knowledge_base_id=knowledge_base_id,
            team_id=team_id,
            score=match.score,
            processed_query=processed_query,
        )
        candidates.append(
            replace(
                base_chunk,
                keyword_score=match.score,
                matched_terms=match.matched_terms,
                candidate_sources=("keyword",),
            )
        )

    candidates.sort(key=lambda item: (-(item.keyword_score or item.score), item.document_id, item.chunk_id))
    return candidates[:effective_top_n]


def _expand_token(token: str) -> list[str]:
    normalized = normalize_text(token)
    expanded = [normalized]
    if PATH_SPLIT_PATTERN.search(normalized):
        expanded.extend(part for part in PATH_SPLIT_PATTERN.split(normalized) if part)
        basename = PATH_SPLIT_PATTERN.split(normalized)[-1]
        if basename:
            expanded.append(basename)
            if "." in basename:
                expanded.append(basename.rsplit(".", 1)[0])
    if "." in normalized:
        expanded.append(normalized.rsplit(".", 1)[0])
    if any(char in normalized for char in ("-", ".", ":", "_")):
        expanded.extend(part for part in TECH_SPLIT_PATTERN.split(normalized) if part)
    if re.fullmatch(r"[\u4e00-\u9fff]+", normalized) and len(normalized) <= 12:
        expanded.extend(normalized[index] for index in range(len(normalized)))
    return expanded


def _metadata_text(chunk: DocumentChunk) -> str:
    return chunk.metadata_json or ""
