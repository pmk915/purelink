from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import (
    DocumentIndexStatus,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.indexing.index_metadata_service import (
    DIMENSION_MISMATCH_REASON,
    LEGACY_UNKNOWN_INDEX_REASON,
    MODEL_MISMATCH_REASON,
    PROVIDER_MISMATCH_REASON,
    STATUS_NOT_INDEXED_REASON,
    filter_documents_with_compatible_vector_index,
    get_vector_index,
    is_vector_index_compatible,
    mark_vector_failed,
    mark_vector_indexed,
    mark_vector_indexing,
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


def test_mark_vector_indexing_creates_row(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        index = mark_vector_indexing(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
            model_version="hashed_bow_v1",
        )
        db.commit()

    assert index.status == DocumentIndexStatus.INDEXING
    assert index.provider == "local_hashed_bow"
    assert index.model_dim == 128


def test_mark_vector_indexed_updates_existing_row(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        mark_vector_indexing(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
        )
        index = mark_vector_indexed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
            model_version="hashed_bow_v1",
        )
        db.commit()

    assert index.status == DocumentIndexStatus.INDEXED
    assert index.indexed_at is not None
    assert index.error_message is None


def test_mark_vector_failed_updates_status_and_error(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        index = mark_vector_failed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
            error_message="embedding failed",
        )
        db.commit()

    assert index.status == DocumentIndexStatus.FAILED
    assert index.error_message == "embedding failed"


@pytest.mark.parametrize(
    ("provider", "model_name", "model_dim", "expected_reason"),
    [
        ("other", "hashed_bow_v1", 128, PROVIDER_MISMATCH_REASON),
        ("local_hashed_bow", "other-model", 128, MODEL_MISMATCH_REASON),
        ("local_hashed_bow", "hashed_bow_v1", 256, DIMENSION_MISMATCH_REASON),
    ],
)
def test_compatibility_fails_for_identity_mismatch(
    session_factory: sessionmaker,
    provider: str,
    model_name: str,
    model_dim: int,
    expected_reason: str,
) -> None:
    with session_factory() as db:
        document = _create_document(db)
        mark_vector_indexed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
        )

        compatible, reason = is_vector_index_compatible(
            db,
            document_id=document.id,
            current_provider=provider,
            current_model_name=model_name,
            current_model_dim=model_dim,
        )

    assert compatible is False
    assert reason == expected_reason


def test_compatibility_passes_for_same_identity(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        mark_vector_indexed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
        )

        compatible, reason = is_vector_index_compatible(
            db,
            document_id=document.id,
            current_provider="local_hashed_bow",
            current_model_name="hashed_bow_v1",
            current_model_dim=128,
        )

    assert compatible is True
    assert reason is None


def test_missing_index_is_allowed_as_legacy_unknown(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)

        compatible, reason = is_vector_index_compatible(
            db,
            document_id=document.id,
            current_provider="local_hashed_bow",
            current_model_name="hashed_bow_v1",
            current_model_dim=128,
        )

    assert compatible is True
    assert reason == LEGACY_UNKNOWN_INDEX_REASON


def test_non_indexed_status_is_incompatible(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        mark_vector_indexing(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
        )

        compatible, reason = is_vector_index_compatible(
            db,
            document_id=document.id,
            current_provider="local_hashed_bow",
            current_model_name="hashed_bow_v1",
            current_model_dim=128,
        )

    assert compatible is False
    assert reason == STATUS_NOT_INDEXED_REASON


def test_filter_documents_allows_legacy_and_skips_incompatible_indexes(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        compatible = _create_document(db, filename="compatible.txt")
        incompatible = _create_document(db, filename="incompatible.txt")
        legacy = _create_document(db, filename="legacy.txt")
        mark_vector_indexed(
            db,
            document_id=compatible.id,
            knowledge_base_id=compatible.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="hashed_bow_v1",
            model_dim=128,
        )
        mark_vector_indexed(
            db,
            document_id=incompatible.id,
            knowledge_base_id=incompatible.knowledge_base_id,
            provider="local_hashed_bow",
            model_name="old-model",
            model_dim=128,
        )

        allowed = filter_documents_with_compatible_vector_index(
            db,
            documents=[compatible, incompatible, legacy],
            current_provider="local_hashed_bow",
            current_model_name="hashed_bow_v1",
            current_model_dim=128,
        )

    assert [item.id for item in allowed] == [compatible.id, legacy.id]


def _create_document(db: Session, *, filename: str = "index-service.txt") -> Document:
    user = db.query(User).first()
    if user is None:
        user = User(
            email="index-service@example.com",
            username="index-service",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.flush()

    knowledge_base = db.query(KnowledgeBase).first()
    if knowledge_base is None:
        knowledge_base = KnowledgeBase(
            name="Index Service KB",
            scope=KnowledgeBaseScope.PERSONAL,
            owner_id=user.id,
        )
        db.add(knowledge_base)
        db.flush()

    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename=filename,
        original_filename=filename,
        file_type="text/plain",
        file_size=64,
        storage_path=f"personal/{filename}",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    assert get_vector_index(db, document_id=document.id) is None
    return document
