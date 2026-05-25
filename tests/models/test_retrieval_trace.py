from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.enums import RetrievalFilteredReason
from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem


load_all_models()


def test_retrieval_trace_and_items_can_be_created() -> None:
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
        with testing_session_local() as db:
            trace = RetrievalTrace(
                user_id=None,
                knowledge_base_id=None,
                query="What is PureLink?",
                mode="chunk_only",
                top_k=8,
                embedding_provider="local_hashed_bow",
                embedding_model="hashed_bow_v1",
            )
            db.add(trace)
            db.flush()
            item = RetrievalTraceItem(
                trace_id=trace.id,
                document_id=None,
                chunk_id=None,
                citation_unit_id=None,
                candidate_text_preview="PureLink trace preview",
                initial_rank=1,
                final_rank=1,
                selected_for_context=True,
                filtered_reason=RetrievalFilteredReason.NOT_FILTERED,
            )
            db.add(item)
            db.commit()
            db.refresh(trace)

            assert trace.id is not None
            assert len(trace.items) == 1
            assert trace.items[0].filtered_reason == RetrievalFilteredReason.NOT_FILTERED
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
