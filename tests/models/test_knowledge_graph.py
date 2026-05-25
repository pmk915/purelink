from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.models.user import User


load_all_models()


def test_knowledge_graph_models_can_link_to_source_evidence() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            document, chunk, unit = _create_document_chunk_and_unit(db)
            source = KnowledgeEntity(
                knowledge_base_id=document.knowledge_base_id,
                name="管理员",
                normalized_name="管理员",
                entity_type="role",
            )
            target = KnowledgeEntity(
                knowledge_base_id=document.knowledge_base_id,
                name="文档",
                normalized_name="文档",
                entity_type="document",
            )
            db.add_all([source, target])
            db.flush()
            relation = KnowledgeRelation(
                knowledge_base_id=document.knowledge_base_id,
                source_entity_id=source.id,
                target_entity_id=target.id,
                relation_type="can_delete",
                source_document_id=document.id,
                source_chunk_id=chunk.id,
                source_citation_unit_id=unit.id,
            )
            mention = EntityMention(
                entity_id=source.id,
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                chunk_id=chunk.id,
                citation_unit_id=unit.id,
                text_span="管理员",
            )
            db.add_all([relation, mention])
            db.flush()

            assert relation.source_chunk_id == chunk.id
            assert relation.source_citation_unit_id == unit.id
            assert mention.entity_id == source.id
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_document_chunk_and_unit(db):
    user = User(email="kg-model@example.com", username="kg-model", hashed_password="hashed")
    db.add(user)
    db.flush()
    kb = KnowledgeBase(name="KG KB", scope=KnowledgeBaseScope.PERSONAL, owner_id=user.id)
    db.add(kb)
    db.flush()
    document = Document(
        knowledge_base_id=kb.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="kg.md",
        original_filename="kg.md",
        file_type="text/markdown",
        file_size=128,
        storage_path="personal/kg.md",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_key=f"document:{document.id}:chunk:0",
        chunk_index=0,
        chunk_text="管理员可以删除文档。",
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
    return document, chunk, unit
