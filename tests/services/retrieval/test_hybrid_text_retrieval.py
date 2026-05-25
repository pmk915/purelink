from __future__ import annotations

from pathlib import Path

import pytest

from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.services.document_embedding import RetrievedChunk
from app.services.retrieval import hybrid_text_retriever
from app.services.retrieval.hybrid_text_retriever import (
    merge_hybrid_text_candidates,
    retrieve_hybrid_text_chunks,
)


def _chunk(
    *,
    chunk_id: str,
    text: str,
    score: float,
    chunk_db_id: int | None = None,
    vector_score: float | None = None,
    keyword_score: float | None = None,
    matched_terms: tuple[str, ...] | None = None,
    candidate_sources: tuple[str, ...] | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_db_id=chunk_db_id,
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=1,
        scope="personal",
        team_id=None,
        document_name="doc.md",
        text=text,
        snippet=text,
        source_type="markdown",
        char_start=None,
        char_end=None,
        page_number=None,
        start_time=None,
        end_time=None,
        section_title=None,
        source_locator=None,
        heading_path=None,
        score=score,
        vector_score=vector_score,
        keyword_score=keyword_score,
        matched_terms=matched_terms,
        candidate_sources=candidate_sources,
    )


def test_merge_preserves_vector_candidate_when_keyword_has_no_match() -> None:
    merged = merge_hybrid_text_candidates(
        vector_candidates=[
            _chunk(
                chunk_id="1:0",
                chunk_db_id=1,
                text="semantic candidate",
                score=0.8,
                vector_score=0.8,
                candidate_sources=("vector",),
            )
        ],
        keyword_candidates=[],
        top_k=3,
    )

    assert len(merged) == 1
    assert merged[0].vector_score == 0.8
    assert merged[0].candidate_sources == ("vector",)


def test_merge_keeps_keyword_only_candidate() -> None:
    merged = merge_hybrid_text_candidates(
        vector_candidates=[],
        keyword_candidates=[
            _chunk(
                chunk_id="1:1",
                chunk_db_id=2,
                text="RERANKER_ENABLED=true",
                score=1.2,
                keyword_score=1.2,
                matched_terms=("reranker_enabled",),
                candidate_sources=("keyword",),
            )
        ],
        top_k=3,
    )

    assert len(merged) == 1
    assert merged[0].keyword_score == 1.2
    assert merged[0].matched_terms == ("reranker_enabled",)
    assert merged[0].candidate_sources == ("keyword",)


def test_merge_dedupes_vector_and_keyword_candidate() -> None:
    merged = merge_hybrid_text_candidates(
        vector_candidates=[
            _chunk(
                chunk_id="1:0",
                chunk_db_id=1,
                text="rag health endpoint",
                score=0.7,
                vector_score=0.7,
                candidate_sources=("vector",),
            )
        ],
        keyword_candidates=[
            _chunk(
                chunk_id="1:0",
                chunk_db_id=1,
                text="rag health endpoint",
                score=1.1,
                keyword_score=1.1,
                matched_terms=("rag-health",),
                candidate_sources=("keyword",),
            )
        ],
        top_k=3,
    )

    assert len(merged) == 1
    assert merged[0].vector_score == 0.7
    assert merged[0].keyword_score == 1.1
    assert merged[0].candidate_sources == ("vector", "keyword")


def test_retrieve_hybrid_falls_back_when_keyword_retriever_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vector_candidate = _chunk(
        chunk_id="1:0",
        text="vector fallback",
        score=0.6,
        vector_score=0.6,
        candidate_sources=("vector",),
    )

    monkeypatch.setattr(
        hybrid_text_retriever.chunk_retriever,
        "retrieve_chunks_for_documents",
        lambda **kwargs: [vector_candidate],
    )

    def raise_keyword_error(**kwargs):
        raise RuntimeError("keyword unavailable")

    monkeypatch.setattr(
        hybrid_text_retriever,
        "retrieve_keyword_chunks",
        raise_keyword_error,
    )

    chunks, metadata = retrieve_hybrid_text_chunks(
        db=object(),
        documents=[],
        vector_root=Path("."),
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=1,
        query="RERANKER_ENABLED",
        top_k=3,
        required_review_status=DocumentReviewStatus.NOT_REQUIRED,
    )

    assert chunks == [vector_candidate]
    assert metadata.keyword_failed is True
    assert "RuntimeError" in (metadata.fallback_reason or "")
