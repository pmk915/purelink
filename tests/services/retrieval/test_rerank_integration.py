from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.services.document_embedding import RetrievedChunk
from app.services.retrieval.retrieval_service import retrieve
from app.services.retrieval.types import RetrievalMode, RetrievalRequest


def _chunk(*, chunk_id: str, text: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        chunk_db_id=int(chunk_id.split(":")[-1]) + 1,
        document_id=1,
        knowledge_base_id=1,
        scope="personal",
        team_id=None,
        document_name="alpha.txt",
        text=text,
        snippet=text,
        source_type="text",
        char_start=None,
        char_end=None,
        page_number=None,
        start_time=None,
        end_time=None,
        section_title=None,
        source_locator=f"text:{chunk_id}",
        heading_path=None,
        score=score,
    )


@pytest.mark.anyio
async def test_retrieval_preserves_order_when_reranker_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setenv("RERANKER_PROVIDER", "noop")
    get_settings.cache_clear()
    captured: dict[str, int] = {}
    chunks = [
        _chunk(chunk_id="1:0", text="General overview."),
        _chunk(chunk_id="1:1", text="Alpha deployment checklist."),
    ]

    def fake_retrieve_chunks_for_documents(**kwargs):  # noqa: ANN003
        captured["top_k"] = kwargs["top_k"]
        return chunks

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        fake_retrieve_chunks_for_documents,
    )

    result = await retrieve(
        RetrievalRequest(
            db=object(),
            documents=[],
            vector_root=tmp_path,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=1,
            user_id=1,
            query="alpha deployment",
            top_k=2,
            mode=RetrievalMode.CHUNK_ONLY,
            include_citations=False,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )
    )

    assert captured["top_k"] == 2
    assert result.used_reranker is False
    assert [item.chunk_id for item in result.evidences] == ["1:0", "1:1"]
    assert all(item.rerank_score is None for item in result.evidences)
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_retrieval_reranks_and_trims_final_evidences(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "local_rule_reranker")
    monkeypatch.setenv("RERANKER_TOP_N", "3")
    get_settings.cache_clear()
    captured: dict[str, int] = {}
    chunks = [
        _chunk(chunk_id="1:0", text="General overview."),
        _chunk(chunk_id="1:1", text="Alpha deployment checklist includes rollback."),
        _chunk(chunk_id="1:2", text="Alpha checklist appendix."),
    ]

    def fake_retrieve_chunks_for_documents(**kwargs):  # noqa: ANN003
        captured["top_k"] = kwargs["top_k"]
        return chunks[: kwargs["top_k"]]

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        fake_retrieve_chunks_for_documents,
    )

    result = await retrieve(
        RetrievalRequest(
            db=object(),
            documents=[],
            vector_root=tmp_path,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=1,
            user_id=1,
            query="alpha deployment checklist",
            top_k=2,
            mode=RetrievalMode.CHUNK_ONLY,
            include_citations=False,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )
    )

    assert captured["top_k"] == 3
    assert result.used_reranker is True
    assert [item.chunk_id for item in result.evidences] == ["1:1", "1:2"]
    assert all(item.rerank_score is not None for item in result.evidences)
    assert "Alpha deployment checklist" in result.context_text
    assert len(result.metadata["retrieved_chunks"]) == 2
    get_settings.cache_clear()
