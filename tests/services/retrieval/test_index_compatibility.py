from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.indexing.index_metadata_service import mark_vector_indexed
from app.services.retrieval.retrieval_service import retrieve
from app.services.retrieval.types import RetrievalRequest


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
async def test_retrieve_filters_incompatible_indexed_documents_but_allows_legacy(
    session_factory: sessionmaker,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_document_ids: list[int] = []

    def fake_retrieve_chunks_for_documents(**kwargs):  # noqa: ANN003
        captured_document_ids.extend(item.id for item in kwargs["documents"])
        return []

    monkeypatch.setattr(
        "app.services.retrieval.retrieval_service.chunk_retriever.retrieve_chunks_for_documents",
        fake_retrieve_chunks_for_documents,
    )

    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        compatible = _create_document(db, user=user, knowledge_base=knowledge_base, filename="compatible.txt")
        incompatible = _create_document(db, user=user, knowledge_base=knowledge_base, filename="incompatible.txt")
        legacy = _create_document(db, user=user, knowledge_base=knowledge_base, filename="legacy.txt")
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

        await retrieve(
            RetrievalRequest(
                query="index compatibility",
                knowledge_base_id=knowledge_base.id,
                user_id=user.id,
                db=db,
                documents=[compatible, incompatible, legacy],
                vector_root=tmp_path,
                scope=KnowledgeBaseScope.PERSONAL,
                required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            )
        )

    assert captured_document_ids == [compatible.id, legacy.id]


def _create_user_and_kb(db: Session) -> tuple[User, KnowledgeBase]:
    user = User(
        email="retrieval-index@example.com",
        username="retrieval-index",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name="Retrieval Index KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    return user, knowledge_base


def _create_document(
    db: Session,
    *,
    user: User,
    knowledge_base: KnowledgeBase,
    filename: str,
) -> Document:
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
    return document
