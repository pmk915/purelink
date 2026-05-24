from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import DocumentIndexStatus, DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.document_indexing import build_document_index
from app.services.document_parsing.block_persistence import list_document_blocks
from app.services.document_processing import process_document
from app.services.indexing.index_metadata_service import get_vector_index


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


def test_process_document_persists_blocks_and_keeps_indexing_working(
    session_factory: sessionmaker,
    tmp_path,
) -> None:
    with session_factory() as db:
        document = _create_uploaded_document(db)
        upload_root = tmp_path / "uploads"
        source = upload_root / document.storage_path
        source.parent.mkdir(parents=True)
        source.write_text("# Title\n\nPureLink stores document blocks.", encoding="utf-8")

        result = process_document(
            db,
            document=document,
            upload_root=upload_root,
        )
        blocks = list_document_blocks(db, document_id=document.id)
        indexed_result = build_document_index(
            db,
            document=document,
            chunks_root=tmp_path / "chunks",
            vector_root=tmp_path / "vector_store",
        )
        index = get_vector_index(db, document_id=document.id)

    assert result.chunk_count >= 1
    assert blocks
    assert blocks[0].text == "Title"
    assert indexed_result.embedded_chunk_count >= 1
    assert index is not None
    assert index.status == DocumentIndexStatus.INDEXED


def _create_uploaded_document(db: Session) -> Document:
    user = User(
        email="block-processing@example.com",
        username="block-processing",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name="Block Processing KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="blocks.md",
        original_filename="blocks.md",
        file_type="text/markdown",
        file_size=64,
        storage_path="personal/blocks.md",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    db.add(document)
    db.flush()
    return document
