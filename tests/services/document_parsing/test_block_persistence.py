from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.document_parsing.block_persistence import (
    list_document_blocks,
    replace_document_blocks,
)
from app.services.document_parsing.types import DocumentBlock, DocumentBlockType


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


def test_replace_document_blocks_replaces_existing_blocks(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document(db)
        replace_document_blocks(
            db,
            document_id=document.id,
            blocks=[
                DocumentBlock(
                    block_type=DocumentBlockType.HEADING,
                    text="Old",
                    order_index=0,
                    heading_level=1,
                )
            ],
        )
        replace_document_blocks(
            db,
            document_id=document.id,
            blocks=[
                DocumentBlock(
                    block_type=DocumentBlockType.TEXT,
                    text="New",
                    order_index=0,
                    metadata={"source_type": "text"},
                )
            ],
        )
        blocks = list_document_blocks(db, document_id=document.id)

    assert len(blocks) == 1
    assert blocks[0].block_type == DocumentBlockType.TEXT
    assert blocks[0].text == "New"
    assert json.loads(blocks[0].metadata_json)["source_type"] == "text"


def _create_document(db: Session) -> Document:
    user = User(
        email="block-user@example.com",
        username="block-user",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name="Blocks KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="blocks.txt",
        original_filename="blocks.txt",
        file_type="text/plain",
        file_size=64,
        storage_path="personal/blocks.txt",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    db.add(document)
    db.flush()
    return document
