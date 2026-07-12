from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.conversation import Conversation
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
    RetrievalFilteredReason,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem
from app.models.user import User
from app.services.document_embedding import RetrievedChunk
from app.services.retrieval.retrieval_service import retrieve
from app.services.retrieval.query_router import route_query as actual_route_query
from app.services.retrieval.types import RetrievalMode, RetrievalRequest


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


@pytest.mark.anyio
async def test_retrieval_returns_trace_id_and_records_selected_evidence(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    def fake_retrieve_chunks_for_documents(**kwargs):  # noqa: ANN003
        return [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-a",
                text="PureLink retrieval trace records selected evidence.",
                score=0.9,
            )
        ]

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        fake_retrieve_chunks_for_documents,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="retrieval trace",
                top_k=3,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )
        trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == result.trace_id))
        items = list(db.scalars(select(RetrievalTraceItem).where(RetrievalTraceItem.trace_id == result.trace_id)))

    assert result.trace_id is not None
    assert trace is not None
    assert trace.initial_candidate_count == 1
    assert trace.final_evidence_count == 1
    assert trace.used_reranker is False
    assert len(items) == 1
    assert items[0].selected_for_context is True
    assert items[0].filtered_reason == RetrievalFilteredReason.NOT_FILTERED
    assert "selected evidence" in items[0].candidate_text_preview


@pytest.mark.anyio
async def test_retrieval_trace_can_be_disabled(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        lambda **kwargs: [],
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="retrieval trace disabled",
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
                enable_trace=False,
            )
        )
        trace_count = len(list(db.scalars(select(RetrievalTrace))))

    assert result.trace_id is None
    assert trace_count == 0


@pytest.mark.anyio
async def test_auto_routing_uses_evidence_query_while_retrieval_uses_augmented_query(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()
    routed_queries: list[str] = []
    retrieved_queries: list[str] = []

    def capture_route_query(query: str):
        routed_queries.append(query)
        return actual_route_query(query)

    def fake_retrieve_chunks_for_documents(**kwargs):  # noqa: ANN003
        retrieved_queries.append(kwargs["query"])
        return [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-current-question",
                text="Alice Chen works in Singapore.",
                score=0.9,
            )
        ]

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.route_query",
        capture_route_query,
    )
    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        fake_retrieve_chunks_for_documents,
    )

    augmented_query = "请总结文档\nRETRIEVAL_MIN_SCORE\nAlice 和 Bob 的关系\nAlice Chen 在哪里办公？"
    current_question = "Alice Chen 在哪里办公？"
    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        conversation = Conversation(
            user_id=user.id,
            knowledge_base_id=knowledge_base.id,
            title="Conversation routing",
        )
        db.add(conversation)
        db.flush()
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                conversation_id=conversation.id,
                query=augmented_query,
                evidence_query=current_question,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )
        trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == result.trace_id))
        trace_metadata = json.loads(trace.metadata_json or "{}") if trace else {}

    assert routed_queries == [current_question]
    assert retrieved_queries == [augmented_query]
    assert result.query == augmented_query
    assert result.requested_mode == RetrievalMode.AUTO
    assert result.selected_mode == RetrievalMode.CHUNK_ONLY
    assert result.router_confidence == "low"
    assert result.metadata["routing_query_source"] == "evidence_query"
    assert trace is not None
    assert trace.query == augmented_query
    assert trace.conversation_id == conversation.id
    assert trace_metadata["routing_query_source"] == "evidence_query"


@pytest.mark.anyio
async def test_retrieval_trace_records_rerank_order_and_non_selected_candidates(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "local_rule_reranker")
    monkeypatch.setenv("RERANKER_MODEL", "local_rule_reranker")
    monkeypatch.setenv("RERANKER_TOP_N", "5")
    get_settings.cache_clear()

    def fake_retrieve_chunks_for_documents(**kwargs):  # noqa: ANN003
        document_id = kwargs["documents"][0].id
        return [
            _retrieved_chunk(
                document_id=document_id,
                chunk_id="chunk-low",
                text="General deployment notes without the target term.",
                score=0.95,
            ),
            _retrieved_chunk(
                document_id=document_id,
                chunk_id="chunk-high",
                text="Alpha target evidence should win local rule reranking.",
                score=0.5,
            ),
        ]

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        fake_retrieve_chunks_for_documents,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="alpha target",
                top_k=1,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )
        trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == result.trace_id))
        items = list(
            db.scalars(
                select(RetrievalTraceItem)
                .where(RetrievalTraceItem.trace_id == result.trace_id)
                .order_by(RetrievalTraceItem.initial_rank.asc())
            )
        )

    get_settings.cache_clear()
    assert trace is not None
    assert trace.used_reranker is True
    assert trace.final_evidence_count == 1
    assert [item.initial_rank for item in items] == [1, 2]
    selected = [item for item in items if item.selected_for_context]
    not_selected = [item for item in items if not item.selected_for_context]
    assert len(selected) == 1
    assert "Alpha target evidence" in selected[0].candidate_text_preview
    assert selected[0].rerank_rank == 1
    assert selected[0].final_rank == 1
    assert selected[0].rerank_score is not None
    assert not_selected[0].filtered_reason == RetrievalFilteredReason.NOT_SELECTED_AFTER_RERANK


@pytest.mark.anyio
async def test_trace_start_failure_does_not_break_retrieval(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.trace_service.start_retrieval_trace",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("trace unavailable")),
    )
    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        lambda **kwargs: [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-a",
                text="Retrieval still returns evidence.",
                score=0.9,
            )
        ],
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="trace unavailable",
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.trace_id is None
    assert result.evidences


@pytest.mark.anyio
async def test_auto_mode_records_selected_mode_and_router_trace_metadata(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    def fake_retrieve_hybrid_text_chunks(**kwargs):  # noqa: ANN003
        return [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-api",
                text="The API path is handled in knowledge base routes.",
                score=0.92,
                candidate_sources=("vector", "keyword"),
            )
        ], SimpleNamespace(keyword_candidate_count=1, keyword_failed=False, fallback_reason=None)

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_hybrid_text_chunks",
        fake_retrieve_hybrid_text_chunks,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="/api/kb/documents 接口在哪里",
                top_k=3,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )
        trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == result.trace_id))

    assert result.requested_mode == RetrievalMode.AUTO
    assert result.selected_mode == RetrievalMode.HYBRID_TEXT
    assert result.mode == RetrievalMode.HYBRID_TEXT
    assert result.router_reason == "question contains exact technical identifier"
    assert result.router_confidence == "high"
    assert result.effective_mode == RetrievalMode.HYBRID_TEXT
    assert result.fallback_mode is None
    assert result.fallback_reason is None
    assert result.metadata["requested_mode"] == "auto"
    assert result.metadata["selected_mode"] == "hybrid_text"
    assert result.metadata["effective_mode"] == "hybrid_text"
    assert result.metadata["router_confidence"] == "high"
    assert result.metadata["fallback_mode"] is None
    assert result.metadata["fallback_reason"] is None
    assert trace is not None
    trace_metadata = json.loads(trace.metadata_json or "{}")
    assert trace_metadata["requested_mode"] == "auto"
    assert trace_metadata["selected_mode"] == "hybrid_text"
    assert trace_metadata["effective_mode"] == "hybrid_text"
    assert trace_metadata["router_type"] == "rule_based"
    assert trace_metadata["router_reason"] == "question contains exact technical identifier"
    assert trace_metadata["router_confidence"] == "high"
    assert trace_metadata["fallback_mode"] is None
    assert trace_metadata["fallback_reason"] is None


@pytest.mark.anyio
async def test_manual_chunk_only_mode_bypasses_auto_router(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        lambda **kwargs: [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-manual",
                text="Manual chunk retrieval result.",
                score=0.9,
            )
        ],
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="/api/kb/documents 接口在哪里",
                top_k=3,
                mode=RetrievalMode.CHUNK_ONLY,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.requested_mode == RetrievalMode.CHUNK_ONLY
    assert result.selected_mode == RetrievalMode.CHUNK_ONLY
    assert result.mode == RetrievalMode.CHUNK_ONLY
    assert result.router_reason == "manual mode specified"
    assert result.router_confidence == "manual"
    assert result.effective_mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_mode is None
    assert result.fallback_reason is None


@pytest.mark.anyio
async def test_manual_hybrid_text_mode_keeps_selected_mode(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    def fake_retrieve_hybrid_text_chunks(**kwargs):  # noqa: ANN003
        return [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-hybrid",
                text="Manual hybrid retrieval result.",
                score=0.88,
                candidate_sources=("vector", "keyword"),
            )
        ], SimpleNamespace(keyword_candidate_count=1, keyword_failed=False, fallback_reason=None)

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_hybrid_text_chunks",
        fake_retrieve_hybrid_text_chunks,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="这个文档说了什么结论",
                top_k=3,
                mode=RetrievalMode.HYBRID_TEXT,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.requested_mode == RetrievalMode.HYBRID_TEXT
    assert result.selected_mode == RetrievalMode.HYBRID_TEXT
    assert result.mode == RetrievalMode.HYBRID_TEXT


@pytest.mark.anyio
async def test_graph_vector_mix_fallbacks_to_chunk_only_when_graph_candidates_empty(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        lambda **kwargs: [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-vector",
                text="Vector fallback relation evidence.",
                score=0.81,
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_graph_chunks",
        lambda **kwargs: [],
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="Alice Chen 和 Bob Li 是什么关系？",
                top_k=3,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )
        trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == result.trace_id))

    trace_metadata = json.loads(trace.metadata_json or "{}")
    assert result.selected_mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert result.mode == RetrievalMode.CHUNK_ONLY
    assert result.effective_mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_reason == "graph_candidates_empty"
    assert result.evidences
    assert result.metadata["selected_mode"] == "graph_vector_mix"
    assert result.metadata["effective_mode"] == "chunk_only"
    assert result.metadata["fallback_mode"] == "chunk_only"
    assert trace_metadata["selected_mode"] == "graph_vector_mix"
    assert trace_metadata["effective_mode"] == "chunk_only"
    assert trace_metadata["fallback_reason"] == "graph_candidates_empty"


@pytest.mark.anyio
async def test_graph_retrieval_failure_fallbacks_to_chunk_only(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        lambda **kwargs: [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-vector",
                text="Vector fallback survives graph failure.",
                score=0.82,
            )
        ],
    )

    def raise_graph_failure(**kwargs):  # noqa: ANN003
        raise RuntimeError("graph unavailable")

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_graph_chunks",
        raise_graph_failure,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="Alice Chen 和 Bob Li 是什么关系？",
                top_k=3,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.selected_mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert result.mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_reason == "graph_retrieval_failed"
    assert result.evidences


@pytest.mark.anyio
async def test_graph_vector_mix_with_graph_candidates_does_not_fallback(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        lambda **kwargs: [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-vector",
                text="Vector relation evidence.",
                score=0.5,
            )
        ],
    )
    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_graph_chunks",
        lambda **kwargs: [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-graph",
                text="Graph relation evidence.",
                score=0.9,
                candidate_sources=("graph",),
            )
        ],
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="Alice Chen 和 Bob Li 是什么关系？",
                top_k=3,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.selected_mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert result.mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert result.fallback_mode is None
    assert result.fallback_reason is None
    assert any("Graph relation evidence" in item.text for item in result.evidences)


@pytest.mark.anyio
async def test_hybrid_text_keyword_empty_records_chunk_only_fallback(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    def fake_retrieve_hybrid_text_chunks(**kwargs):  # noqa: ANN003
        return [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-vector",
                text="Vector candidate remains available.",
                score=0.8,
                candidate_sources=("vector",),
            )
        ], SimpleNamespace(keyword_candidate_count=0, keyword_failed=False, fallback_reason=None)

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_hybrid_text_chunks",
        fake_retrieve_hybrid_text_chunks,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="RETRIEVAL_MIN_SCORE 默认值是什么？",
                top_k=3,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.selected_mode == RetrievalMode.HYBRID_TEXT
    assert result.mode == RetrievalMode.CHUNK_ONLY
    assert result.effective_mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_reason == "keyword_candidates_empty"
    assert result.evidences


@pytest.mark.anyio
async def test_hybrid_text_keyword_failure_records_chunk_only_fallback(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    get_settings.cache_clear()

    def fake_retrieve_hybrid_text_chunks(**kwargs):  # noqa: ANN003
        return [
            _retrieved_chunk(
                document_id=kwargs["documents"][0].id,
                chunk_id="chunk-vector",
                text="Vector candidate survives keyword failure.",
                score=0.8,
                candidate_sources=("vector",),
            )
        ], SimpleNamespace(keyword_candidate_count=0, keyword_failed=True, fallback_reason="RuntimeError: boom")

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.retrieve_hybrid_text_chunks",
        fake_retrieve_hybrid_text_chunks,
    )

    with session_factory() as db:
        user, knowledge_base, document = _create_user_kb_document(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                query="RETRIEVAL_MIN_SCORE 默认值是什么？",
                top_k=3,
                mode=RetrievalMode.AUTO,
                include_citations=False,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert result.selected_mode == RetrievalMode.HYBRID_TEXT
    assert result.mode == RetrievalMode.CHUNK_ONLY
    assert result.fallback_reason == "keyword_retrieval_failed"
    assert result.evidences


def _create_user_kb_document(db: Session) -> tuple[User, KnowledgeBase, Document]:
    user = User(
        email="trace-integration@example.com",
        username="trace-integration",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name="Trace Integration KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="trace.txt",
        original_filename="trace.txt",
        file_type="text/plain",
        file_size=64,
        storage_path="personal/trace.txt",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    return user, knowledge_base, document


def _retrieved_chunk(
    *,
    document_id: int,
    chunk_id: str,
    text: str,
    score: float,
    candidate_sources: tuple[str, ...] = (),
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        knowledge_base_id=1,
        scope=KnowledgeBaseScope.PERSONAL.value,
        team_id=None,
        document_name="trace.txt",
        text=text,
        snippet=text,
        source_type="text",
        char_start=None,
        char_end=None,
        page_number=None,
        start_time=None,
        end_time=None,
        section_title=None,
        source_locator=None,
        heading_path=None,
        score=score,
        chunk_db_id=None,
        candidate_sources=candidate_sources,
    )
