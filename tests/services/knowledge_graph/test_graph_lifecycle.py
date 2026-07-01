from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.document_index import DocumentIndex
from app.models.enums import (
    DocumentIndexStatus,
    DocumentIndexType,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.models.user import User
from app.services.document import delete_document_and_artifacts
from app.services.knowledge_graph.graph_export_service import export_graph
from app.services.knowledge_graph.graph_index_service import (
    cleanup_orphan_entities,
    deduplicate_relations,
    delete_document_graph,
    rebuild_document_graph,
)


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


def test_delete_document_graph_preserves_shared_entity_and_other_relation_source(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        fixture = _create_graph_fixture(db)
        db.add(
            EntityMention(
                entity_id=fixture["shared_entity"].id,
                knowledge_base_id=fixture["kb"].id,
                document_id=fixture["doc_2"].id,
                chunk_id=fixture["chunk_2"].id,
                citation_unit_id=fixture["unit_2"].id,
                text_span="文档",
            )
        )
        db.add(
            KnowledgeRelation(
                knowledge_base_id=fixture["kb"].id,
                source_entity_id=fixture["admin_entity"].id,
                target_entity_id=fixture["shared_entity"].id,
                relation_type="can_delete",
                source_document_id=fixture["doc_2"].id,
                source_chunk_id=fixture["chunk_2"].id,
                source_citation_unit_id=fixture["unit_2"].id,
            )
        )
        db.commit()

        result = delete_document_graph(db, document_id=fixture["doc_1"].id)
        db.commit()

        remaining_mentions = list(db.scalars(select(EntityMention)))
        remaining_relations = list(db.scalars(select(KnowledgeRelation)))
        remaining_entities = list(db.scalars(select(KnowledgeEntity)))

    assert result.deleted_mentions == 2
    assert result.deleted_relation_sources == 1
    assert all(item.document_id != fixture["doc_1"].id for item in remaining_mentions)
    assert {item.source_document_id for item in remaining_relations} == {fixture["doc_2"].id}
    assert fixture["shared_entity"].id in {item.id for item in remaining_entities}


def test_cleanup_orphan_entities_deletes_only_unreferenced_entities(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        fixture = _create_graph_fixture(db)
        orphan = KnowledgeEntity(
            knowledge_base_id=fixture["kb"].id,
            name="Orphan",
            normalized_name="orphan",
            entity_type="concept",
        )
        db.add(orphan)
        db.commit()

        result = cleanup_orphan_entities(db, kb_id=fixture["kb"].id)
        db.commit()

        entity_names = {item.name for item in db.scalars(select(KnowledgeEntity))}

    assert result.deleted_orphan_entities == 1
    assert "Orphan" not in entity_names
    assert "文档" in entity_names


def test_deduplicate_relations_removes_duplicate_evidence_without_losing_other_sources(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        fixture = _create_graph_fixture(db)
        duplicate = KnowledgeRelation(
            knowledge_base_id=fixture["kb"].id,
            source_entity_id=fixture["admin_entity"].id,
            target_entity_id=fixture["shared_entity"].id,
            relation_type="can_delete",
            source_document_id=fixture["doc_1"].id,
            source_chunk_id=fixture["chunk_1"].id,
            source_citation_unit_id=fixture["unit_1"].id,
        )
        other_source = KnowledgeRelation(
            knowledge_base_id=fixture["kb"].id,
            source_entity_id=fixture["admin_entity"].id,
            target_entity_id=fixture["shared_entity"].id,
            relation_type="can_delete",
            source_document_id=fixture["doc_2"].id,
            source_chunk_id=fixture["chunk_2"].id,
            source_citation_unit_id=fixture["unit_2"].id,
        )
        db.add_all([duplicate, other_source])
        db.commit()

        result = deduplicate_relations(db, kb_id=fixture["kb"].id)
        db.commit()

        remaining_sources = {
            item.source_document_id
            for item in db.scalars(select(KnowledgeRelation).order_by(KnowledgeRelation.id.asc()))
        }

    assert result.deleted_duplicate_relations == 1
    assert remaining_sources == {fixture["doc_1"].id, fixture["doc_2"].id}


def test_rebuild_document_graph_uses_existing_chunks_and_keeps_vector_index(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        fixture = _create_graph_fixture(db)
        vector_index = DocumentIndex(
            document_id=fixture["doc_1"].id,
            knowledge_base_id=fixture["kb"].id,
            index_type=DocumentIndexType.VECTOR,
            status=DocumentIndexStatus.INDEXED,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
        )
        db.add(vector_index)
        db.commit()
        vector_index_id = vector_index.id

        result = rebuild_document_graph(db, document_id=fixture["doc_1"].id)
        db.commit()

        relations = list(
            db.scalars(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.source_document_id == fixture["doc_1"].id
                )
            )
        )
        saved_vector_index = db.get(DocumentIndex, vector_index_id)

    assert result is not None
    assert result.deleted_mentions == 2
    assert result.created_mentions > 0
    assert result.created_relations > 0
    assert relations
    assert saved_vector_index is not None
    assert saved_vector_index.status == DocumentIndexStatus.INDEXED


def test_export_graph_returns_entities_relations_and_limited_sources(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        fixture = _create_graph_fixture(db)
        result = export_graph(
            db,
            kb_id=fixture["kb"].id,
            entity_limit=10,
            relation_limit=10,
            sources_per_relation=3,
        )

    assert result.kb_id == fixture["kb"].id
    assert result.entities
    assert result.relations
    assert result.relations[0].sources
    assert result.relations[0].sources[0].filename == "doc-1.md"
    assert result.relations[0].sources[0].snippet


def test_delete_document_and_artifacts_cleans_graph_data(
    session_factory: sessionmaker,
    tmp_path: Path,
) -> None:
    with session_factory() as db:
        fixture = _create_graph_fixture(db)
        document_id = fixture["doc_1"].id
        upload_root = tmp_path / "uploads"
        parsed_root = tmp_path / "parsed"
        chunks_root = tmp_path / "chunks"
        (upload_root / fixture["doc_1"].storage_path).parent.mkdir(parents=True)
        (upload_root / fixture["doc_1"].storage_path).write_text("source")

        delete_document_and_artifacts(
            db,
            document=fixture["doc_1"],
            scope=KnowledgeBaseScope.PERSONAL,
            upload_root=upload_root,
            parsed_root=parsed_root,
            chunks_root=chunks_root,
        )

        remaining_mentions = list(
            db.scalars(select(EntityMention).where(EntityMention.document_id == document_id))
        )
        remaining_relations = list(
            db.scalars(
                select(KnowledgeRelation).where(
                    KnowledgeRelation.source_document_id == document_id
                )
            )
        )

    assert remaining_mentions == []
    assert remaining_relations == []


def _create_graph_fixture(db: Session) -> dict[str, object]:
    user = User(email="graph-lifecycle@example.com", username="graph-life", hashed_password="hashed")
    db.add(user)
    db.flush()
    kb = KnowledgeBase(name="Graph Lifecycle KB", scope=KnowledgeBaseScope.PERSONAL, owner_id=user.id)
    db.add(kb)
    db.flush()
    doc_1, chunk_1, unit_1 = _create_document_with_chunk(
        db,
        kb=kb,
        user=user,
        filename="doc-1.md",
        text="管理员可以删除文档，普通成员可以上传文档。",
        index=1,
    )
    doc_2, chunk_2, unit_2 = _create_document_with_chunk(
        db,
        kb=kb,
        user=user,
        filename="doc-2.md",
        text="文档属于知识库，GraphRAG 关联 citation。",
        index=2,
    )
    admin_entity = KnowledgeEntity(
        knowledge_base_id=kb.id,
        name="管理员",
        normalized_name="管理员",
        entity_type="role",
    )
    shared_entity = KnowledgeEntity(
        knowledge_base_id=kb.id,
        name="文档",
        normalized_name="文档",
        entity_type="document",
    )
    db.add_all([admin_entity, shared_entity])
    db.flush()
    db.add_all(
        [
            EntityMention(
                entity_id=admin_entity.id,
                knowledge_base_id=kb.id,
                document_id=doc_1.id,
                chunk_id=chunk_1.id,
                citation_unit_id=unit_1.id,
                text_span="管理员",
            ),
            EntityMention(
                entity_id=shared_entity.id,
                knowledge_base_id=kb.id,
                document_id=doc_1.id,
                chunk_id=chunk_1.id,
                citation_unit_id=unit_1.id,
                text_span="文档",
            ),
            KnowledgeRelation(
                knowledge_base_id=kb.id,
                source_entity_id=admin_entity.id,
                target_entity_id=shared_entity.id,
                relation_type="can_delete",
                source_document_id=doc_1.id,
                source_chunk_id=chunk_1.id,
                source_citation_unit_id=unit_1.id,
            ),
        ]
    )
    db.commit()
    return {
        "kb": kb,
        "doc_1": doc_1,
        "doc_2": doc_2,
        "chunk_1": chunk_1,
        "chunk_2": chunk_2,
        "unit_1": unit_1,
        "unit_2": unit_2,
        "admin_entity": admin_entity,
        "shared_entity": shared_entity,
    }


def _create_document_with_chunk(
    db: Session,
    *,
    kb: KnowledgeBase,
    user: User,
    filename: str,
    text: str,
    index: int,
) -> tuple[Document, DocumentChunk, DocumentCitationUnit]:
    document = Document(
        knowledge_base_id=kb.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename=filename,
        original_filename=filename,
        file_type="text/markdown",
        file_size=len(text),
        storage_path=f"personal/knowledge_base_{kb.id}/{filename}",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_key=f"document:{document.id}:chunk:0",
        chunk_index=0,
        chunk_text=text,
    )
    db.add(chunk)
    db.flush()
    unit = DocumentCitationUnit(
        document_id=document.id,
        chunk_id=chunk.id,
        knowledge_base_id=kb.id,
        chunk_key=chunk.chunk_key,
        unit_index=index,
        unit_text=text,
    )
    db.add(unit)
    db.flush()
    return document, chunk, unit
