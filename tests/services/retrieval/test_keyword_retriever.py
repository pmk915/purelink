from __future__ import annotations

from app.services.retrieval.keyword_retriever import (
    extract_query_terms,
    score_keyword_match,
)


def test_extracts_env_var_tokens() -> None:
    terms = extract_query_terms("RERANKER_ENABLED 是什么？")

    assert "reranker_enabled" in terms
    assert "reranker" in terms
    assert "enabled" in terms


def test_extracts_api_path_tokens() -> None:
    terms = extract_query_terms("/api/v1/knowledge-bases/{id}/rag-health 返回什么？")

    assert "/api/v1/knowledge-bases/{id}/rag-health" in terms
    assert "knowledge-bases" in terms
    assert "rag-health" in terms


def test_extracts_file_path_tokens() -> None:
    terms = extract_query_terms("app/services/retrieval/rerank_service.py 负责什么？")

    assert "app/services/retrieval/rerank_service.py" in terms
    assert "rerank_service.py" in terms
    assert "rerank_service" in terms


def test_extracts_migration_id_tokens() -> None:
    terms = extract_query_terms("20260525_0020 migration 是干什么的？")

    assert "20260525_0020" in terms


def test_keyword_score_positive_when_terms_match() -> None:
    terms = extract_query_terms("RERANKER_ENABLED")
    match = score_keyword_match(
        query="RERANKER_ENABLED",
        query_terms=terms,
        chunk_text="Set RERANKER_ENABLED=true to enable the optional reranker.",
        document_name="model-providers.md",
    )

    assert match.score > 0
    assert "reranker_enabled" in match.matched_terms


def test_keyword_score_zero_when_unrelated() -> None:
    terms = extract_query_terms("RERANKER_ENABLED")
    match = score_keyword_match(
        query="RERANKER_ENABLED",
        query_terms=terms,
        chunk_text="Team members can upload documents after joining a workspace.",
    )

    assert match.score == 0
    assert match.matched_terms == ()


def test_document_name_match_boosts_score() -> None:
    terms = extract_query_terms("rerank_service.py")
    text_only = score_keyword_match(
        query="rerank_service.py",
        query_terms=terms,
        chunk_text="This module handles retrieval scoring.",
    )
    with_document_name = score_keyword_match(
        query="rerank_service.py",
        query_terms=terms,
        chunk_text="This module handles retrieval scoring.",
        document_name="app/services/retrieval/rerank_service.py",
    )

    assert with_document_name.score > text_only.score
