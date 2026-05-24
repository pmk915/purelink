from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.enums import RetrievalFilteredReason
from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem
from app.services.retrieval.trace_service import (
    finish_retrieval_trace,
    record_retrieval_trace_items,
    start_retrieval_trace,
    truncate_candidate_preview,
)
from app.services.retrieval.trace_types import RetrievalTraceCandidate


load_all_models()


@pytest.fixture
def session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield testing_session_local
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_start_and_finish_retrieval_trace(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        trace = start_retrieval_trace(
            db,
            user_id=None,
            knowledge_base_id=None,
            query="trace query",
            mode="chunk_only",
            top_k=3,
            embedding_provider="local_hashed_bow",
            embedding_model="hashed_bow_v1",
            reranker_enabled=True,
            reranker_provider="local_rule_reranker",
            reranker_model="local_rule_reranker",
        )
        finish_retrieval_trace(
            db,
            trace_id=trace.id,
            initial_candidate_count=4,
            final_evidence_count=2,
            used_reranker=True,
            metadata={"stage": "done"},
        )
        saved = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == trace.id))

    assert saved is not None
    assert saved.initial_candidate_count == 4
    assert saved.final_evidence_count == 2
    assert saved.used_reranker is True
    assert saved.completed_at is not None
    assert json.loads(saved.metadata_json)["stage"] == "done"


def test_record_retrieval_trace_items_truncates_preview(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        trace = start_retrieval_trace(
            db,
            user_id=None,
            knowledge_base_id=None,
            query="trace query",
            mode="chunk_only",
            top_k=3,
        )
        record_retrieval_trace_items(
            db,
            trace_id=trace.id,
            candidates=[
                RetrievalTraceCandidate(
                    document_id=1,
                    candidate_text_preview="x" * 80,
                    initial_rank=1,
                    final_rank=1,
                    selected_for_context=True,
                    filtered_reason=RetrievalFilteredReason.NOT_FILTERED,
                    metadata={"marker": "S1"},
                )
            ],
            preview_max_chars=20,
        )
        item = db.scalar(select(RetrievalTraceItem).where(RetrievalTraceItem.trace_id == trace.id))

    assert item is not None
    assert item.candidate_text_preview == "x" * 17 + "..."
    assert item.selected_for_context is True
    assert json.loads(item.metadata_json)["marker"] == "S1"


def test_record_empty_trace_items_is_noop(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        trace = start_retrieval_trace(
            db,
            user_id=None,
            knowledge_base_id=None,
            query="trace query",
            mode="chunk_only",
            top_k=3,
        )
        record_retrieval_trace_items(db, trace_id=trace.id, candidates=[])
        count = len(list(db.scalars(select(RetrievalTraceItem))))

    assert count == 0


def test_truncate_candidate_preview_normalizes_whitespace() -> None:
    assert truncate_candidate_preview("a\n b\tc", max_chars=20) == "a b c"
