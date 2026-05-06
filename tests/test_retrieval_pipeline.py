from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
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
from app.services.overview_retrieval import (
    collect_overview_chunks,
    is_near_duplicate,
    overview_score_chunk,
)
from app.services.qa import (
    MessageContext,
    NO_RELIABLE_EVIDENCE_MESSAGE,
    answer_question,
    build_conversation_retrieval_query,
    extract_used_citation_ids,
    load_citation_units_for_chunks,
    select_context_chunks_for_answer,
    select_evidence_units,
)
from app.services.qa_intent import QAIntent, classify_qa_intent
from app.services.retrieval import (
    build_query_aware_chunk_snippet,
    merge_hybrid_candidates,
    preprocess_retrieval_query,
    retrieve_chunks_for_documents,
    search_document_chunks_lexical,
)


load_all_models()


class StaticAnswerGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, *, question: str, evidence_units, prompt) -> str:  # noqa: ANN001
        return self.answer


class CapturingAnswerGenerator:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.last_prompt = None

    def generate(self, *, question: str, evidence_units, prompt) -> str:  # noqa: ANN001
        self.last_prompt = prompt
        return self.answer


def test_classify_qa_intent_routes_fact_and_overview_questions() -> None:
    assert classify_qa_intent("乌萨奇长啥样？") == QAIntent.KB_FACT_QA
    assert classify_qa_intent("乌萨奇是什么颜色？") == QAIntent.KB_FACT_QA
    assert classify_qa_intent("总结这个知识库的主要内容") == QAIntent.KB_OVERVIEW
    assert classify_qa_intent("这个知识库里有哪些关键点？") == QAIntent.KB_OVERVIEW
    assert classify_qa_intent("梳理这些文档") == QAIntent.KB_OVERVIEW


def test_build_conversation_retrieval_query_uses_recent_messages_for_follow_up() -> None:
    retrieval_query = build_conversation_retrieval_query(
        question="那它叫什么名字？",
        recent_messages=[
            MessageContext(role="user", content="乌萨奇长啥样？"),
            MessageContext(role="assistant", content="乌萨奇是明黄色的小兔子，有粉色内耳 [S1]。"),
        ],
    )

    assert "乌萨奇长啥样？" in retrieval_query
    assert "乌萨奇是明黄色的小兔子" in retrieval_query
    assert "那它叫什么名字？" in retrieval_query
    assert "[S1]" not in retrieval_query


def test_overview_score_chunk_prefers_overview_section_title_over_boilerplate(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="overview-score.txt",
        )
        overview_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=5,
            chunk_text="本节概述 PureLink 的核心能力，包括队列处理、语义检索和引用回答。",
            metadata={"source_type": "text", "section_title": "概述"},
        )
        toc_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="目录 第一章 引言 第二章 架构设计 第三章 参考文献。",
            metadata={"source_type": "text", "section_title": "目录"},
        )

        overview_score = overview_score_chunk(
            overview_chunk,
            document_name=document.original_filename,
        )
        toc_score = overview_score_chunk(
            toc_chunk,
            document_name=document.original_filename,
        )

    assert overview_score > toc_score


def test_collect_overview_chunks_prefers_overview_sections_over_table_of_contents(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="overview-sections.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="目录 第一章 引言 第二章 部署 第三章 参考文献。",
            metadata={"source_type": "text", "section_title": "目录"},
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="本节概述了 PureLink 的整体能力，包括上传、索引和知识库问答。",
            metadata={"source_type": "text", "section_title": "概述"},
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=2,
            chunk_text="正文详细说明 ProcessingJob、Worker 和 Redis 队列的协作方式。",
            metadata={"source_type": "text", "section_title": "正文"},
        )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=[document],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            max_chunks=2,
            max_chunks_per_document=2,
        )

    assert chunks
    assert any(item.section_title == "概述" for item in chunks)
    assert chunks[0].section_title != "目录"


def test_collect_overview_chunks_balances_documents(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        documents = [
            _create_document(
                db,
                user=user,
                knowledge_base=knowledge_base,
                original_filename=f"balanced-{index}.txt",
                processing_status=DocumentProcessingStatus.INDEXED,
            )
            for index in range(3)
        ]
        for index, document in enumerate(documents):
            for chunk_index in range(3):
                _create_chunk(
                    db,
                    document=document,
                    chunk_index=chunk_index,
                    chunk_text=(
                        f"文档 {index} 的第 {chunk_index} 段，概述 PureLink 在场景 {index} 中的能力。"
                    ),
                    metadata={
                        "source_type": "text",
                        "section_title": "概述" if chunk_index == 0 else f"正文 {chunk_index}",
                    },
                )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=documents,
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            max_chunks=6,
            max_chunks_per_document=2,
        )

    assert len(chunks) <= 6
    counts_by_document: dict[int, int] = {}
    for chunk in chunks:
        counts_by_document[chunk.document_id] = counts_by_document.get(chunk.document_id, 0) + 1
    assert all(count <= 2 for count in counts_by_document.values())
    assert set(counts_by_document) == {item.id for item in documents}


def test_collect_overview_chunks_deduplicates_near_duplicate_chunks(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="dedup-overview.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="PureLink 支持上传、索引、检索和带引用的问答能力。",
            metadata={"source_type": "text", "section_title": "概述"},
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="PureLink 支持上传、索引、检索和带引用的问答能力。 这是几乎相同的改写。",
            metadata={"source_type": "text", "section_title": "概述扩展"},
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=2,
            chunk_text="ProcessingJob 用来持久化任务状态，Worker 负责后台执行。",
            metadata={"source_type": "text", "section_title": "任务系统"},
        )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=[document],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            max_chunks=3,
            max_chunks_per_document=3,
        )

    assert len(chunks) == 2
    assert is_near_duplicate(
        "PureLink 支持上传、索引、检索和带引用的问答能力。",
        ["PureLink 支持上传、索引、检索和带引用的问答能力。 这是几乎相同的改写。"],
    )


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
    processing_status: DocumentProcessingStatus = DocumentProcessingStatus.INDEXED,
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


def _create_citation_unit(
    db: Session,
    *,
    document: Document,
    chunk_key: str,
    unit_index: int,
    unit_text: str,
    metadata: dict[str, object] | None = None,
    start_char: int | None = None,
    end_char: int | None = None,
) -> DocumentCitationUnit:
    parent_chunk = db.scalar(
        select(DocumentChunk).where(
            DocumentChunk.document_id == document.id,
            DocumentChunk.chunk_key == chunk_key,
        )
    )
    if parent_chunk is None:
        chunk_index = int(chunk_key.rsplit(":", maxsplit=1)[-1]) if ":" in chunk_key else 0
        parent_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=chunk_index,
            chunk_text=unit_text,
            metadata=metadata,
        )
    unit = DocumentCitationUnit(
        document_id=document.id,
        chunk_id=parent_chunk.id,
        knowledge_base_id=document.knowledge_base_id,
        chunk_key=chunk_key,
        unit_index=unit_index,
        unit_text=unit_text,
        start_char=start_char,
        end_char=end_char,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.add(unit)
    db.flush()
    return unit


def _retrieved_chunk(
    *,
    chunk_id: str,
    document_id: int,
    document_name: str,
    score: float,
    chunk_db_id: int | None = None,
    text: str = "PureLink knowledge base chunk text",
    section_title: str | None = None,
    heading_path: tuple[str, ...] | None = None,
    source_type: str | None = "text",
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
        chunk_db_id=chunk_db_id,
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
            metadata={"source_type": "text"},
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="Unrelated release timeline entry.",
            metadata={"source_type": "text"},
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
        "开场说明。"
        + ("前文 " * 50)
        + "critical recovery token appears in this middle sentence."
        + ("后文 " * 50)
        + "结尾说明。"
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
    assert "middle sentence." in snippet


def test_build_query_aware_chunk_snippet_preserves_sentence_boundary_near_anchor() -> None:
    text = (
        "前置说明。"
        "乌萨奇拥有除草检定5级证照。"
        "乌萨奇通常有粉色内耳、圆眼睛和白色尾巴。"
        "结尾说明。"
    )
    processed_query = preprocess_retrieval_query("乌萨奇长啥样")

    snippet = build_query_aware_chunk_snippet(
        text,
        processed_query=processed_query,
        max_length=36,
    )

    assert "粉色内耳" in snippet
    assert not snippet.endswith("耳")
    assert snippet.endswith(("。", "..."))


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
            metadata={"source_type": "text"},
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
            metadata={"source_type": "text"},
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
                                    "metadata": {"source_type": "text"},
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
            metadata={"source_type": "text"},
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
                                    "metadata": {"source_type": "text"},
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


def test_answer_question_returns_empty_citations_when_scores_are_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVAL_MIN_SCORE", "0.2")
    get_settings.cache_clear()

    result = answer_question(
        question="What does the runbook say?",
        retrieved_chunks=[
            _retrieved_chunk(
                chunk_id="1:0",
                document_id=1,
                document_name="runbook.txt",
                score=0.08,
                text="Rollback checklist for the service.",
            )
        ],
    )

    get_settings.cache_clear()
    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []
    assert result.intent == QAIntent.KB_FACT_QA.value


def test_answer_question_includes_recent_conversation_in_prompt_but_keeps_evidence_boundary(
    session_factory: sessionmaker,
) -> None:
    generator = CapturingAnswerGenerator("乌萨奇叫乌萨奇 [S1]。")

    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="乌萨奇.txt",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:0",
            unit_index=0,
            unit_text="乌萨奇的名字是乌萨奇。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="那它叫什么名字？",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=f"{document.id}:0",
                    document_id=document.id,
                    document_name="乌萨奇.txt",
                    score=0.93,
                    text="乌萨奇的名字是乌萨奇。",
                )
            ],
            conversation_context=[
                MessageContext(role="user", content="乌萨奇长啥样？"),
                MessageContext(role="assistant", content="乌萨奇是明黄色的小兔子，有粉色内耳 [S1]。"),
            ],
            generator=generator,
        )

    assert result.answer == "乌萨奇叫乌萨奇 [S1]。"
    assert generator.last_prompt is not None
    assert "Recent Conversation:" in generator.last_prompt.user_prompt
    assert "乌萨奇长啥样？" in generator.last_prompt.user_prompt
    assert "Evidence Units:" in generator.last_prompt.user_prompt
    assert "不可作为事实依据" in generator.last_prompt.system_prompt


def test_answer_question_does_not_treat_history_as_evidence_without_current_support() -> None:
    result = answer_question(
        question="那它叫什么名字？",
        retrieved_chunks=[],
        conversation_context=[
            MessageContext(role="user", content="乌萨奇长啥样？"),
            MessageContext(role="assistant", content="乌萨奇叫乌萨奇 [S1]。"),
        ],
        generator=StaticAnswerGenerator("乌萨奇叫乌萨奇 [S1]。"),
    )

    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []


def test_extract_used_citation_ids_normalizes_multiple_marker_formats() -> None:
    answer = "乌萨奇是蓝色兔子外型 [S1]。它有粉色内耳 [1][S2]。另见 [1, 2]。"

    assert extract_used_citation_ids(answer) == ["S1", "S2"]


def test_answer_question_binds_claims_to_used_evidence_markers(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="乌萨奇.txt",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:0",
            unit_index=0,
            unit_text="乌萨奇是蓝色兔子外型。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:1",
            unit_index=1,
            unit_text="乌萨奇有粉色内耳。",
            metadata={"source_type": "text", "source_locator": "text:chunk:1"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="乌萨奇长什么样？",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=f"{document.id}:0",
                    document_id=document.id,
                    document_name="乌萨奇.txt",
                    score=0.93,
                    text="乌萨奇是蓝色兔子外型。",
                ),
                _retrieved_chunk(
                    chunk_id=f"{document.id}:1",
                    document_id=document.id,
                    document_name="乌萨奇.txt",
                    score=0.91,
                    text="乌萨奇有粉色内耳。",
                ),
            ],
            generator=StaticAnswerGenerator(
                "乌萨奇是蓝色兔子外型 [S1]。它有粉色内耳 [S2]。"
            ),
        )

    assert result.answer == "乌萨奇是蓝色兔子外型 [S1]。它有粉色内耳 [S2]。"
    assert [item.citation_marker for item in result.citations] == ["S1", "S2"]
    assert [item.snippet for item in result.citations] == [
        "乌萨奇是蓝色兔子外型。",
        "乌萨奇有粉色内耳。",
    ]
    assert result.intent == QAIntent.KB_FACT_QA.value


def test_answer_question_returns_no_reliable_context_when_answer_has_no_valid_markers(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="乌萨奇.txt",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:0",
            unit_index=0,
            unit_text="乌萨奇只是角色之一。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="乌萨奇有没有白色尾巴？",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=f"{document.id}:0",
                    document_id=document.id,
                    document_name="乌萨奇.txt",
                    score=0.93,
                    text="乌萨奇只是角色之一。",
                )
            ],
            generator=StaticAnswerGenerator("乌萨奇有白色尾巴 [S99]。"),
        )

    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []
    assert result.intent == QAIntent.KB_FACT_QA.value


def test_answer_question_routes_overview_questions_to_indexed_document_chunks(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document_a = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="overview-a.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        document_b = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="overview-b.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        chunk_a = _create_chunk(
            db,
            document=document_a,
            chunk_index=0,
            chunk_text="第一份文档介绍 Redis 只负责触发 worker。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        chunk_b = _create_chunk(
            db,
            document=document_b,
            chunk_index=0,
            chunk_text="第二份文档介绍 ProcessingJob 保存任务事实来源。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        _create_citation_unit(
            db,
            document=document_a,
            chunk_key=chunk_a.chunk_key,
            unit_index=0,
            unit_text="第一份文档介绍 Redis 只负责触发 worker。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        _create_citation_unit(
            db,
            document=document_b,
            chunk_key=chunk_b.chunk_key,
            unit_index=0,
            unit_text="第二份文档介绍 ProcessingJob 保存任务事实来源。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="总结这个知识库的主要内容",
            retrieved_chunks=[],
            documents=[document_a, document_b],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            generator=StaticAnswerGenerator(
                "- 资料说明 Redis 只负责触发 worker [S1]\n"
                "- 资料说明 ProcessingJob 保存任务事实来源 [S2]"
            ),
        )

    assert result.intent == QAIntent.KB_OVERVIEW.value
    assert result.answer
    assert "[S1]" in result.answer
    assert len(result.citations) == 2
    assert {item.document_id for item in result.citations} == {document_a.id, document_b.id}


def test_answer_question_routes_overview_questions_with_conversation_history_without_biasing_to_last_topic(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document_a = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="appearance.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        document_b = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="series.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        chunk_a = _create_chunk(
            db,
            document=document_a,
            chunk_index=0,
            chunk_text="这份文档介绍乌萨奇的外貌特征，包括明黄色外形和粉色内耳。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0", "section_title": "外貌"},
        )
        chunk_b = _create_chunk(
            db,
            document=document_b,
            chunk_index=0,
            chunk_text="这份文档介绍乌萨奇所属作品、角色定位以及系列背景。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0", "section_title": "背景"},
        )
        _create_citation_unit(
            db,
            document=document_a,
            chunk_key=chunk_a.chunk_key,
            unit_index=0,
            unit_text="这份文档介绍乌萨奇的外貌特征，包括明黄色外形和粉色内耳。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0", "section_title": "外貌"},
        )
        _create_citation_unit(
            db,
            document=document_b,
            chunk_key=chunk_b.chunk_key,
            unit_index=0,
            unit_text="这份文档介绍乌萨奇所属作品、角色定位以及系列背景。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0", "section_title": "背景"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="这个知识库有哪些关键点？",
            retrieved_chunks=[],
            documents=[document_a, document_b],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            conversation_context=[
                MessageContext(role="user", content="乌萨奇长啥样？"),
                MessageContext(role="assistant", content="乌萨奇有明黄色外形 [S1]。"),
            ],
            generator=StaticAnswerGenerator(
                "- 一份资料介绍乌萨奇的外貌特征 [S1]\n"
                "- 另一份资料介绍乌萨奇所属作品和系列背景 [S2]"
            ),
        )

    assert result.intent == QAIntent.KB_OVERVIEW.value
    assert len(result.citations) == 2
    assert {item.document_id for item in result.citations} == {document_a.id, document_b.id}


def test_answer_question_overview_returns_no_reliable_context_without_indexed_documents(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="overview-empty.txt",
            processing_status=DocumentProcessingStatus.READY,
        )
        db.commit()

        result = answer_question(
            db=db,
            question="梳理这些文档",
            retrieved_chunks=[],
            documents=[document],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            generator=StaticAnswerGenerator("- 这里本来不该成功 [S1]"),
        )

    assert result.intent == QAIntent.KB_OVERVIEW.value
    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []


def test_load_citation_units_for_chunks_prefers_chunk_db_id(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="architecture.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Redis 只负责触发，ProcessingJob 保存事实来源。",
            metadata={"source_type": "text"},
        )
        unit = _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Redis 只负责触发，ProcessingJob 保存事实来源。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        db.commit()

        units_by_chunk = load_citation_units_for_chunks(
            db=db,
            chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=chunk.id,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.9,
                    text=chunk.chunk_text,
                )
            ],
        )

    assert chunk.chunk_key in units_by_chunk
    assert units_by_chunk[chunk.chunk_key][0].id == unit.id


def test_load_citation_units_for_chunks_falls_back_to_chunk_key_when_db_id_missing(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="fallback.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Redis 只负责触发。",
            metadata={"source_type": "text"},
        )
        unit = _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Redis 只负责触发。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        db.commit()

        units_by_chunk = load_citation_units_for_chunks(
            db=db,
            chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=None,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.8,
                    text=chunk.chunk_text,
                )
            ],
        )

    assert chunk.chunk_key in units_by_chunk
    assert units_by_chunk[chunk.chunk_key][0].id == unit.id


def test_answer_question_prefers_citation_unit_snippets(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="runbook.docx",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:0",
            unit_index=0,
            unit_text="Redis 只保存 job_id，ProcessingJob 才是任务事实来源。",
            metadata={
                "source_type": "docx",
                "section_title": "任务可靠性设计",
                "source_locator": "section:任务可靠性设计",
                "heading_path": ["任务可靠性设计"],
            },
            start_char=12,
            end_char=42,
        )
        db.commit()

        result = answer_question(
            db=db,
            question="PureLink 的任务可靠性怎么保证？",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=f"{document.id}:0",
                    document_id=document.id,
                    document_name="runbook.docx",
                    score=0.92,
                    text="长 chunk 文本，不应该直接作为最终 citation snippet。",
                    source_type="docx",
                    section_title="任务可靠性设计",
                )
            ],
        )

    assert result.citations
    citation = result.citations[0]
    assert citation.citation_unit_id is not None
    assert citation.chunk_id == f"{document.id}:0"
    assert citation.snippet == "Redis 只保存 job_id，ProcessingJob 才是任务事实来源。"
    assert citation.section_title == "任务可靠性设计"


def test_select_evidence_units_reranks_chinese_appearance_query() -> None:
    retrieved_chunks = [
        _retrieved_chunk(
            chunk_id="1:0",
            document_id=1,
            document_name="乌萨奇.txt",
            score=0.91,
            text="乌萨奇的外貌特征是蓝色兔子外型。",
        ),
        _retrieved_chunk(
            chunk_id="2:0",
            document_id=2,
            document_name="乌萨奇设定.txt",
            score=0.9,
            text="乌萨奇拥有除草检定5级证照。",
        ),
    ]

    evidence_units = select_evidence_units(
        question="乌萨奇长啥样",
        retrieved_chunks=retrieved_chunks,
        chunk_units={},
        max_evidence_units=4,
    )

    assert evidence_units
    assert evidence_units[0].chunk_id == "1:0"
    assert evidence_units[0].lexical_relevance > evidence_units[1].lexical_relevance


def test_answer_question_supports_multi_document_citations(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document_a = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="doc-a.txt",
        )
        document_b = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="doc-b.txt",
        )
        _create_citation_unit(
            db,
            document=document_a,
            chunk_key=f"{document_a.id}:0",
            unit_index=0,
            unit_text="Redis 只作为任务触发器。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        _create_citation_unit(
            db,
            document=document_b,
            chunk_key=f"{document_b.id}:0",
            unit_index=0,
            unit_text="ProcessingJob 是任务事实来源。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="PureLink 的任务可靠性怎么保证？",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=f"{document_a.id}:0",
                    document_id=document_a.id,
                    document_name="doc-a.txt",
                    score=0.93,
                    text="Redis 只作为任务触发器。",
                ),
                _retrieved_chunk(
                    chunk_id=f"{document_b.id}:0",
                    document_id=document_b.id,
                    document_name="doc-b.txt",
                    score=0.91,
                    text="ProcessingJob 是任务事实来源。",
                ),
            ],
        )

    assert len(result.citations) >= 2
    assert {item.document_id for item in result.citations[:2]} == {document_a.id, document_b.id}


def test_answer_question_supports_same_document_multiple_chunk_citations(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="architecture.txt",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:0",
            unit_index=0,
            unit_text="PureLink 使用 Redis 作为任务触发器。",
            metadata={"source_type": "text", "source_locator": "text:chunk:0"},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=f"{document.id}:1",
            unit_index=1,
            unit_text="PureLink 使用 ProcessingJob 保存任务状态。",
            metadata={"source_type": "text", "source_locator": "text:chunk:1"},
        )
        db.commit()

        result = answer_question(
            db=db,
            question="PureLink 的 Redis 和 ProcessingJob 分别有什么作用？",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=f"{document.id}:0",
                    document_id=document.id,
                    document_name="architecture.txt",
                    score=0.95,
                    text="PureLink 使用 Redis 作为任务触发器。",
                ),
                _retrieved_chunk(
                    chunk_id=f"{document.id}:1",
                    document_id=document.id,
                    document_name="architecture.txt",
                    score=0.93,
                    text="PureLink 使用 ProcessingJob 保存任务状态。",
                ),
            ],
        )

    assert len(result.citations) >= 2
    assert result.citations[0].document_id == document.id
    assert result.citations[1].document_id == document.id
    assert {item.chunk_id for item in result.citations[:2]} == {f"{document.id}:0", f"{document.id}:1"}


def test_answer_question_falls_back_to_chunk_level_citation_when_units_are_missing() -> None:
    result = answer_question(
        question="What does the runbook say?",
        retrieved_chunks=[
            _retrieved_chunk(
                chunk_id="1:0",
                document_id=1,
                document_name="runbook.txt",
                score=0.81,
                text="Fallback chunk snippet remains available when units are missing.",
            )
        ],
    )

    assert result.citations
    citation = result.citations[0]
    assert citation.citation_unit_id is None
    assert citation.chunk_id == "1:0"
    assert citation.snippet == "Fallback chunk snippet remains available when units are missing."


def test_answer_question_chunk_level_fallback_uses_sentence_aligned_snippet() -> None:
    result = answer_question(
        question="乌萨奇长啥样？",
        retrieved_chunks=[
            RetrievedChunk(
                chunk_id="1:0",
                document_id=1,
                knowledge_base_id=1,
                scope=KnowledgeBaseScope.PERSONAL.value,
                team_id=None,
                document_name="乌萨奇.txt",
                text="乌萨奇通常有粉色内耳、圆眼睛和白色尾巴。它还拥有除草检定5级证照。",
                snippet="乌萨奇通常有粉色内耳、圆眼",
                source_type="text",
                char_start=0,
                char_end=40,
                page_number=None,
                start_time=None,
                end_time=None,
                section_title=None,
                source_locator=None,
                heading_path=None,
                score=0.88,
            )
        ],
    )

    assert result.citations
    citation = result.citations[0]
    assert citation.citation_unit_id is None
    assert citation.snippet.endswith("。")
    assert "粉色内耳" in citation.snippet
    assert "圆眼睛" in citation.snippet
