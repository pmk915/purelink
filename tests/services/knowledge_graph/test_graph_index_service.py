from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentIndexStatus, DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.models.user import User
from app.services.indexing.index_metadata_service import get_graph_index
from app.services.knowledge_graph.graph_index_service import build_document_graph_index


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


def test_build_document_graph_index_creates_entities_mentions_relations(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_indexed_document_with_evidence(db)
        result = build_document_graph_index(db, document=document)
        graph_index = get_graph_index(db, document_id=document.id)
        entities = list(db.scalars(select(KnowledgeEntity)))
        mentions = list(db.scalars(select(EntityMention)))
        relations = list(db.scalars(select(KnowledgeRelation)))

    assert result.entity_count >= 2
    assert result.mention_count >= 2
    assert result.relation_count >= 1
    assert graph_index is not None
    assert graph_index.status == DocumentIndexStatus.INDEXED
    assert {item.normalized_name for item in entities} >= {"管理员", "文档"}
    assert mentions
    assert any(item.relation_type == "can_delete" for item in relations)
    assert all(item.source_document_id == document.id for item in relations)


def test_build_document_graph_index_replaces_previous_document_graph(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_indexed_document_with_evidence(db)
        build_document_graph_index(db, document=document)
        first_relation_count = len(list(db.scalars(select(KnowledgeRelation))))
        build_document_graph_index(db, document=document)
        second_relation_count = len(list(db.scalars(select(KnowledgeRelation))))

    assert first_relation_count > 0
    assert second_relation_count == first_relation_count


def _create_indexed_document_with_evidence(db: Session) -> Document:
    user = User(email="kg-index@example.com", username="kg-index", hashed_password="hashed")
    db.add(user)
    db.flush()
    kb = KnowledgeBase(name="KG Index KB", scope=KnowledgeBaseScope.PERSONAL, owner_id=user.id)
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
    unit = DocumentCitationUnit(
        document_id=document.id,
        chunk_id=chunk.id,
        knowledge_base_id=kb.id,
        chunk_key=chunk.chunk_key,
        unit_index=0,
        unit_text=chunk.chunk_text,
    )
    db.add(unit)
    db.flush()
    return document
