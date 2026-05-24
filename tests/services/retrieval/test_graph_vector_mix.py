from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.knowledge_graph.graph_index_service import build_document_graph_index
from app.services.retrieval import RetrievalMode, RetrievalRequest, retrieve


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
async def test_graph_vector_mix_falls_back_to_vector_when_graph_missing(
    session_factory: sessionmaker,
    tmp_path,
) -> None:
    with session_factory() as db:
        document = _create_indexed_document_with_evidence(db)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path / "vector_store",
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=document.knowledge_base_id,
                user_id=document.owner_id,
                query="管理员 删除 文档",
                mode=RetrievalMode.GRAPH_VECTOR_MIX,
                top_k=4,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
                enable_trace=False,
            )
        )

    assert result.mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert result.evidences
    assert result.metadata["graph_chunks"] == []


@pytest.mark.anyio
async def test_graph_vector_mix_includes_graph_candidates_and_preserves_citations(
    session_factory: sessionmaker,
    tmp_path,
) -> None:
    with session_factory() as db:
        document = _create_indexed_document_with_evidence(db)
        build_document_graph_index(db, document=document)
        result = await retrieve(
            RetrievalRequest(
                db=db,
                documents=[document],
                vector_root=tmp_path / "vector_store",
                scope=KnowledgeBaseScope.PERSONAL,
                knowledge_base_id=document.knowledge_base_id,
                user_id=document.owner_id,
                query="谁可以删除文档？",
                mode=RetrievalMode.GRAPH_VECTOR_MIX,
                top_k=4,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
                enable_trace=False,
            )
        )

    assert result.mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert result.evidences
    assert any(item.graph_score is not None for item in result.evidences)
    assert any(item.citation_unit_id is not None for item in result.evidences)
    assert result.metadata["graph_chunks"]


def _create_indexed_document_with_evidence(db: Session) -> Document:
    user = User(email="kg-retrieval@example.com", username="kg-retrieval", hashed_password="hashed")
    db.add(user)
    db.flush()
    kb = KnowledgeBase(name="KG Retrieval KB", scope=KnowledgeBaseScope.PERSONAL, owner_id=user.id)
    db.add(kb)
    db.flush()
    document = Document(
        knowledge_base_id=kb.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="permissions.md",
        original_filename="permissions.md",
        file_type="text/markdown",
        file_size=128,
        storage_path="personal/permissions.md",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_key=f"document:{document.id}:chunk:0",
        chunk_index=0,
        chunk_text="管理员可以删除团队文档，普通成员可以上传文档。",
    )
    db.add(chunk)
    db.flush()
    db.add(
        DocumentCitationUnit(
            document_id=document.id,
            chunk_id=chunk.id,
            knowledge_base_id=kb.id,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text=chunk.chunk_text,
        )
    )
    db.flush()
    return document
