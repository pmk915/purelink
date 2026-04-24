from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.document_embedding import DocumentEmbeddingError, RetrievedChunk
from app.services.document_embedding import build_index_relative_path
from app.services.qa import select_context_chunks_for_answer
from app.services.retrieval import (
    build_query_aware_chunk_snippet,
    merge_hybrid_candidates,
    preprocess_retrieval_query,
    retrieve_chunks_for_documents,
    search_document_chunks_lexical,
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


def _create_user_and_kb(db: Session) -> tuple[User, KnowledgeBase]:
    user = User(
        email="retrieval-user@example.com",
        username="retrieval-user",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()

    knowledge_base = KnowledgeBase(
        name="Retrieval KB",
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
    original_filename: str,
    processing_status: DocumentProcessingStatus = DocumentProcessingStatus.READY,
) -> Document:
    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename=original_filename,
        original_filename=original_filename,
        file_type="text/plain",
        file_size=128,
        storage_path=f"personal/knowledge_base_{knowledge_base.id}/{original_filename}",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=processing_status,
    )
    db.add(document)
    db.flush()
    return document


def _create_chunk(
    db: Session,
    *,
    document: Document,
    chunk_index: int,
    chunk_text: str,
    metadata: dict[str, object] | None = None,
) -> DocumentChunk:
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_key=f"{document.id}:{chunk_index}",
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.add(chunk)
    db.flush()
    return chunk


def _retrieved_chunk(
    *,
    chunk_id: str,
    document_id: int,
    document_name: str,
    score: float,
    text: str = "PureLink knowledge base chunk text",
    section_title: str | None = None,
    heading_path: tuple[str, ...] | None = None,
    source_type: str | None = "txt",
    char_start: int | None = None,
    char_end: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        knowledge_base_id=1,
        scope=KnowledgeBaseScope.PERSONAL.value,
        team_id=None,
        document_name=document_name,
        text=text,
        snippet=text,
        source_type=source_type,
        char_start=char_start,
        char_end=char_end,
        page_number=None,
        start_time=None,
        end_time=None,
        section_title=section_title,
        source_locator=None,
        heading_path=heading_path,
        score=score,
    )


def test_preprocess_retrieval_query_normalizes_whitespace_and_case() -> None:
    processed = preprocess_retrieval_query("  PureLink   PDF   Page  1  ")
    assert processed.normalized_text == "purelink pdf page 1"
    assert "purelink" in processed.tokens
    assert "pdf" in processed.unique_tokens
    assert "1" in processed.tokens


def test_search_document_chunks_lexical_returns_keyword_matches(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="incident.txt",
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="PureLink incident runbook contains omega restart checklist.",
            metadata={"source_type": "txt"},
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="Unrelated release timeline entry.",
            metadata={"source_type": "txt"},
        )
        db.commit()

        processed_query = preprocess_retrieval_query("omega runbook")
        results = search_document_chunks_lexical(
            db,
            document_ids={document.id},
            document_lookup={document.id: document},
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            processed_query=processed_query,
            limit=5,
        )

    assert results
    assert results[0].chunk_id == f"{document.id}:0"
    assert results[0].score > 0


def test_hybrid_merge_uses_metadata_to_break_ties() -> None:
    processed_query = preprocess_retrieval_query("runbook")
    chunk_with_title = _retrieved_chunk(
        chunk_id="1:0",
        document_id=1,
        document_name="doc-a.md",
        score=0.40,
        section_title="Runbook",
        heading_path=("Operations", "Runbook"),
    )
    chunk_without_title = _retrieved_chunk(
        chunk_id="2:0",
        document_id=2,
        document_name="doc-b.md",
        score=0.40,
        section_title=None,
        heading_path=None,
    )

    merged = merge_hybrid_candidates(
        vector_candidates=[chunk_with_title, chunk_without_title],
        lexical_candidates=[chunk_with_title, chunk_without_title],
        processed_query=processed_query,
        indexed_document_ids=set(),
        top_k=2,
    )

    assert len(merged) == 2
    assert merged[0].chunk_id == "1:0"
    assert merged[0].score > merged[1].score


def test_hybrid_merge_keeps_indexed_priority_bonus() -> None:
    processed_query = preprocess_retrieval_query("architecture")
    ready_chunk = _retrieved_chunk(
        chunk_id="10:0",
        document_id=10,
        document_name="ready.txt",
        score=0.50,
    )
    indexed_chunk = _retrieved_chunk(
        chunk_id="20:0",
        document_id=20,
        document_name="indexed.txt",
        score=0.50,
    )

    merged = merge_hybrid_candidates(
        vector_candidates=[ready_chunk, indexed_chunk],
        lexical_candidates=[ready_chunk, indexed_chunk],
        processed_query=processed_query,
        indexed_document_ids={20},
        top_k=2,
    )

    assert len(merged) == 2
    assert merged[0].document_id == 20
    assert merged[0].score > merged[1].score


def test_build_query_aware_chunk_snippet_centers_on_query_term() -> None:
    text = (
        "intro " * 80
        + "critical recovery token appears in this middle sentence "
        + "tail " * 80
    )
    processed_query = preprocess_retrieval_query("recovery token")
    snippet = build_query_aware_chunk_snippet(
        text,
        processed_query=processed_query,
        max_length=180,
    )

    assert "recovery token" in snippet.lower()
    assert snippet.startswith("...")
    assert snippet.endswith("...")


def test_retrieve_falls_back_to_lexical_chunks_when_index_is_unavailable(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="indexed.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Fallback lexical retrieval survives a corrupt vector index.",
            metadata={"source_type": "txt"},
        )
        db.commit()

        def fail_search_index(*args, **kwargs):
            raise DocumentEmbeddingError("Vector index is not valid.")

        monkeypatch.setattr("app.services.retrieval.search_index", fail_search_index)

        results = retrieve_chunks_for_documents(
            db=db,
            documents=[document],
            vector_root=tmp_path,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query="fallback lexical",
            top_k=3,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )

    assert results
    assert results[0].document_id == document.id
    assert "Fallback lexical retrieval" in results[0].text


def test_retrieve_falls_back_when_index_provider_config_is_unavailable(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hashed_bow")
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    from app.core.config import get_settings

    get_settings.cache_clear()
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="external-index.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Provider mismatch fallback keeps lexical retrieval available.",
            metadata={"source_type": "txt"},
        )
        db.commit()

        index_path = tmp_path / build_index_relative_path(
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
        )
        index_path.parent.mkdir(parents=True)
        index_path.write_text(
            json.dumps(
                {
                    "index_scheme": "json_vector_index_v1",
                    "embedding_scheme": "openai_compatible_embedding_v1",
                    "embedding_provider": "openai_compatible",
                    "embedding_model": "semantic-model",
                    "embedding_version": "semantic-model",
                    "embedding_dimension": 3,
                    "documents": [
                        {
                            "document_id": document.id,
                            "document_name": document.original_filename,
                            "chunks": [
                                {
                                    "chunk_id": f"{document.id}:0",
                                    "text": "Provider mismatch fallback keeps lexical retrieval available.",
                                    "vector": [1.0, 0.0, 0.0],
                                    "metadata": {"source_type": "txt"},
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        results = retrieve_chunks_for_documents(
            db=db,
            documents=[document],
            vector_root=tmp_path,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query="provider mismatch fallback",
            top_k=3,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )

    get_settings.cache_clear()
    assert results
    assert results[0].document_id == document.id
    assert "Provider mismatch fallback" in results[0].text


def test_retrieve_falls_back_when_index_model_does_not_match_current_provider(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_API_BASE", "https://embedding.example/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "semantic-v2")

    from app.core.config import get_settings

    get_settings.cache_clear()
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="model-mismatch.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Model mismatch fallback keeps lexical retrieval available.",
            metadata={"source_type": "txt"},
        )
        db.commit()

        index_path = tmp_path / build_index_relative_path(
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
        )
        index_path.parent.mkdir(parents=True)
        index_path.write_text(
            json.dumps(
                {
                    "index_scheme": "json_vector_index_v1",
                    "embedding_scheme": "openai_compatible_embedding_v1",
                    "embedding_provider": "openai_compatible",
                    "embedding_model": "semantic-v1",
                    "embedding_version": "semantic-v1",
                    "embedding_dimension": 3,
                    "documents": [
                        {
                            "document_id": document.id,
                            "document_name": document.original_filename,
                            "chunks": [
                                {
                                    "chunk_id": f"{document.id}:0",
                                    "text": "Model mismatch fallback keeps lexical retrieval available.",
                                    "vector": [1.0, 0.0, 0.0],
                                    "metadata": {"source_type": "txt"},
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        results = retrieve_chunks_for_documents(
            db=db,
            documents=[document],
            vector_root=tmp_path,
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query="model mismatch fallback",
            top_k=3,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
        )

    get_settings.cache_clear()
    assert results
    assert results[0].document_id == document.id
    assert "Model mismatch fallback" in results[0].text


def test_select_context_chunks_for_answer_deduplicates_overlapping_chunks() -> None:
    chunks = [
        _retrieved_chunk(
            chunk_id="1:0",
            document_id=1,
            document_name="a.txt",
            score=0.95,
            text="PureLink keeps architecture docs for the platform team.",
            char_start=0,
            char_end=80,
        ),
        _retrieved_chunk(
            chunk_id="1:0",
            document_id=1,
            document_name="a.txt",
            score=0.94,
            text="PureLink keeps architecture docs for the platform team.",
            char_start=0,
            char_end=80,
        ),
        _retrieved_chunk(
            chunk_id="1:1",
            document_id=1,
            document_name="a.txt",
            score=0.90,
            text="PureLink keeps architecture docs for the platform team and release notes.",
            char_start=20,
            char_end=90,
        ),
        _retrieved_chunk(
            chunk_id="2:0",
            document_id=2,
            document_name="b.txt",
            score=0.88,
            text="Team runbook explains rollback and deployment checks.",
            char_start=0,
            char_end=60,
        ),
    ]

    selected = select_context_chunks_for_answer(
        chunks,
        max_chunks=4,
        max_total_chars=4000,
        max_chunks_per_document=3,
    )

    selected_ids = [item.chunk_id for item in selected]
    assert "1:0" in selected_ids
    assert "2:0" in selected_ids
    assert "1:1" not in selected_ids
    assert selected_ids.count("1:0") == 1
