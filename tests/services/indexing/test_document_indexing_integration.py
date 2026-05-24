from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentIndexStatus,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.document_indexing import build_document_index
from app.services.indexing.index_metadata_service import get_graph_index, get_vector_index


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


def test_build_document_index_writes_vector_index_metadata(
    session_factory: sessionmaker,
    tmp_path,
) -> None:
    with session_factory() as db:
        document = _create_ready_document_with_chunk(db)

        result = build_document_index(
            db,
            document=document,
            chunks_root=tmp_path / "chunks",
            vector_root=tmp_path / "vector_store",
        )

        index = get_vector_index(db, document_id=document.id)
        graph_index = get_graph_index(db, document_id=document.id)

    assert result.embedding_provider == "local_hashed_bow"
    assert index is not None
    assert index.status == DocumentIndexStatus.INDEXED
    assert index.provider == "local_hashed_bow"
    assert index.model_name == "hashed_bow_v1"
    assert index.model_dim == 128
    assert index.indexed_at is not None
    assert graph_index is not None
    assert graph_index.status == DocumentIndexStatus.INDEXED


def _create_ready_document_with_chunk(db: Session) -> Document:
    user = User(
        email="indexing-integration@example.com",
        username="indexing-integration",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name="Indexing Integration KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="indexed.txt",
        original_filename="indexed.txt",
        file_type="text/plain",
        file_size=64,
        storage_path="personal/indexed.txt",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.READY,
    )
    db.add(document)
    db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_key=f"{document.id}:0",
            chunk_index=0,
            chunk_text="PureLink stores vector index metadata after indexing.",
            metadata_json='{"source_type":"text"}',
        )
    )
    db.flush()
    return document
