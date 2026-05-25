from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_index import DocumentIndex
from app.models.enums import (
    DocumentIndexStatus,
    DocumentIndexType,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User


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


def test_document_index_can_be_created(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        index = DocumentIndex(
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            index_type=DocumentIndexType.VECTOR,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
            model_version="hashed_bow_v1",
            status=DocumentIndexStatus.INDEXED,
        )
        db.add(index)
        db.commit()
        db.refresh(index)

    assert index.id is not None
    assert index.index_type == DocumentIndexType.VECTOR
    assert index.status == DocumentIndexStatus.INDEXED


def test_document_index_unique_document_and_type_is_enforced(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        document = _create_document(db)
        db.add_all(
            [
                DocumentIndex(
                    document_id=document.id,
                    knowledge_base_id=document.knowledge_base_id,
                    index_type=DocumentIndexType.VECTOR,
                    provider="local_hashed_bow",
                    model_name="hashed_bow_v1",
                    status=DocumentIndexStatus.INDEXED,
                ),
                DocumentIndex(
                    document_id=document.id,
                    knowledge_base_id=document.knowledge_base_id,
                    index_type=DocumentIndexType.VECTOR,
                    provider="local_hashed_bow",
                    model_name="hashed_bow_v1",
                    status=DocumentIndexStatus.INDEXED,
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            db.commit()


def _create_document(db: Session) -> Document:
    user = User(
        email="index-model@example.com",
        username="index-model",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name="Index Model KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="index-model.txt",
        original_filename="index-model.txt",
        file_type="text/plain",
        file_size=64,
        storage_path="personal/index-model.txt",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    return document
