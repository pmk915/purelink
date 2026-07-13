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
from app.models.document_block import DocumentBlock
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.retrieval_trace import RetrievalTrace
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.qa import CitationRead
from app.services.document_embedding import DocumentEmbeddingError, RetrievedChunk
from app.services.document_embedding import build_index_relative_path
from app.services.document_processing import process_document
from app.services.evidence_support import evaluate_evidence_support
from app.services.overview_retrieval import (
    collect_overview_chunks,
    is_near_duplicate,
    overview_score_chunk,
)
from app.services.qa import (
    HeuristicAnswerGenerator,
    MessageContext,
    NO_RELIABLE_EVIDENCE_MESSAGE,
    answer_question,
    build_citation_ready_fallback_units,
    build_conversation_retrieval_query,
    build_fact_prompt,
    extract_used_citation_ids,
    load_citation_units_for_chunks,
    select_context_chunks_for_answer,
    select_evidence_units,
)
from app.services.qa_intent import QAIntent, classify_qa_intent
from app.services.retrieval import (
    RetrievalMode,
    RetrievalResult,
    build_query_aware_chunk_snippet,
    merge_hybrid_candidates,
    preprocess_retrieval_query,
    retrieve_chunks_for_documents,
    search_document_chunks_lexical,
)
from app.services.retrieval.citation_builder import build_evidences


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
        self.last_evidence_units = None
        self.call_count = 0

    def generate(self, *, question: str, evidence_units, prompt) -> str:  # noqa: ANN001
        self.call_count += 1
        self.last_prompt = prompt
        self.last_evidence_units = list(evidence_units)
        return self.answer


class RaisingAnswerGenerator:
    def __init__(self) -> None:
        self.call_count = 0

    def generate(self, *, question: str, evidence_units, prompt) -> str:  # noqa: ANN001
        self.call_count += 1
        raise RuntimeError("provider failed")


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


def test_collect_overview_chunks_prioritizes_relevant_document_in_kb_wide_scope(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        unrelated = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="database-concurrency.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        team_document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="engineering-team-roles.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        for document, text in (
            (unrelated, "Database concurrency overview."),
            (team_document, "Alice, Bob, and Carol are engineering team members."),
        ):
            _create_chunk(
                db,
                document=document,
                chunk_index=0,
                chunk_text=text,
                metadata={"source_type": "text", "section_title": "Overview"},
            )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=[unrelated, team_document],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            query="当前语料中的团队成员有哪些？",
            max_chunks=1,
            max_chunks_per_document=1,
        )

    assert len(chunks) == 1
    assert chunks[0].document_id == team_document.id


def test_collect_overview_chunks_limits_candidates_to_target_document(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        target = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="python-classes.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        unrelated = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="postgresql-concurrency.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        for document, text in (
            (target, "Python classes organize data and behavior. Inheritance reuses behavior."),
            (unrelated, "PostgreSQL uses MVCC and locks for concurrency control."),
        ):
            _create_chunk(
                db,
                document=document,
                chunk_index=0,
                chunk_text=text,
                metadata={"source_type": "text", "section_title": "Overview"},
            )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=[target, unrelated],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            target_document_ids=(target.id,),
            overview_scope="document_targeted",
            target_document_requested=True,
            max_chunks=4,
            max_chunks_per_document=2,
        )

    assert chunks
    assert {item.document_id for item in chunks} == {target.id}
    assert all("PostgreSQL" not in item.text for item in chunks)


def test_collect_overview_chunks_balances_multiple_target_documents(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        documents = [
            _create_document(
                db,
                user=user,
                knowledge_base=knowledge_base,
                original_filename=f"target-{index}.txt",
                processing_status=DocumentProcessingStatus.INDEXED,
            )
            for index in range(3)
        ]
        for index, document in enumerate(documents):
            _create_chunk(
                db,
                document=document,
                chunk_index=0,
                chunk_text=f"Target document {index} overview content.",
                metadata={"source_type": "text", "section_title": "Overview"},
            )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=documents,
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            target_document_ids=(documents[0].id, documents[2].id),
            overview_scope="document_targeted",
            target_document_requested=True,
            max_chunks=4,
            max_chunks_per_document=2,
        )

    assert {item.document_id for item in chunks} == {documents[0].id, documents[2].id}


def test_collect_overview_chunks_does_not_fallback_for_unmatched_target(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="existing.txt",
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Existing document overview must not be used as fallback.",
            metadata={"source_type": "text", "section_title": "Overview"},
        )
        db.commit()

        chunks = collect_overview_chunks(
            db=db,
            documents=[document],
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
            target_document_ids=(),
            overview_scope="document_targeted",
            target_document_requested=True,
        )

    assert chunks == []


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
    page_number: int | None = None,
    source_locator: str | None = None,
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
        page_number=page_number,
        start_time=None,
        end_time=None,
        section_title=section_title,
        source_locator=source_locator,
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


def test_minimum_score_citation_survives_processing_persistence_and_evidence(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHUNK_STRATEGY", "block_aware")
    get_settings.cache_clear()
    source_path = Path(__file__).parent / "eval/corpus/purelink_retrieval.txt"
    stored_path = tmp_path / source_path.name
    stored_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

    try:
        with session_factory() as db:
            user, knowledge_base = _create_user_and_kb(db)
            document = _create_document(
                db,
                user=user,
                knowledge_base=knowledge_base,
                original_filename=stored_path.name,
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
            document.storage_path = stored_path.name
            process_document(db, document=document, upload_root=tmp_path)
            db.commit()
            document_id = document.id

        with session_factory() as db:
            blocks = list(
                db.scalars(
                    select(DocumentBlock)
                    .where(DocumentBlock.document_id == document_id)
                    .order_by(DocumentBlock.order_index.asc())
                )
            )
            canonical_text = "\n\n".join(block.text for block in blocks)
            unit = next(
                item
                for item in db.scalars(
                    select(DocumentCitationUnit)
                    .where(DocumentCitationUnit.document_id == document_id)
                    .order_by(DocumentCitationUnit.unit_index.asc())
                )
                if "RETRIEVAL_MIN_SCORE defaults to 0.15" in item.unit_text
            )
            chunk = db.get(DocumentChunk, unit.chunk_id)
            assert chunk is not None
            unit_metadata = json.loads(unit.metadata_json or "{}")
            chunk_metadata = json.loads(chunk.metadata_json or "{}")
            retrieved = _retrieved_chunk(
                chunk_id=chunk.chunk_key,
                chunk_db_id=chunk.id,
                document_id=document_id,
                document_name=stored_path.name,
                score=0.95,
                text=chunk.chunk_text,
                section_title=chunk_metadata.get("section_title"),
                heading_path=tuple(chunk_metadata.get("heading_path") or ()),
                source_type=chunk_metadata.get("source_type"),
                char_start=chunk_metadata.get("char_start"),
                char_end=chunk_metadata.get("char_end"),
                source_locator=chunk_metadata.get("source_locator"),
            )
            candidates = build_citation_ready_fallback_units(
                question="RETRIEVAL_MIN_SCORE 默认值是什么？",
                retrieved_chunks=[retrieved],
                chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
            )
            evidences = build_evidences(candidates)
            support = evaluate_evidence_support(
                query="RETRIEVAL_MIN_SCORE 默认值是什么？",
                evidence_units=evidences,
            )
            prompt = build_fact_prompt(
                question="RETRIEVAL_MIN_SCORE 默认值是什么？",
                evidence_units=candidates,
            )

        selected_candidate = next(
            item for item in candidates if item.citation_unit_id == unit.id
        )
        selected_evidence = next(
            item for item in evidences if item.citation_unit_id == unit.id
        )
        assert unit.id is not None
        assert unit_metadata["section_title"] == "Minimum Score"
        assert unit_metadata["heading_path"] == ["PureLink Retrieval", "Minimum Score"]
        assert unit_metadata["source_locator"] == "section:Minimum Score"
        assert unit.start_char is not None and unit.end_char is not None
        assert canonical_text[unit.start_char:unit.end_char] == unit.unit_text
        assert "RETRIEVAL_MIN_SCORE" in unit.unit_text
        assert "0.15" in unit.unit_text
        assert "defaults to 0." not in unit.unit_text.replace("0.15", "")
        assert selected_candidate.text == unit.unit_text
        assert selected_evidence.text == unit.unit_text
        assert f"content: {unit.unit_text}" in prompt.user_prompt
        assert support.answerable is True
        assert support.reason == "supported"
    finally:
        get_settings.cache_clear()


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


def test_select_context_chunks_for_answer_promotes_explicit_relation_fact() -> None:
    chunks = [
        _retrieved_chunk(
            chunk_id="1:0",
            document_id=1,
            document_name="alice.md",
            score=0.96,
            text="Title: Alice in Wonderland. Type: character reference.",
            section_title="Source metadata",
        ),
        _retrieved_chunk(
            chunk_id="1:1",
            document_id=1,
            document_name="alice.md",
            score=0.94,
            text="Alice is the main character in the story.",
            section_title="Alice",
        ),
        _retrieved_chunk(
            chunk_id="1:2",
            document_id=1,
            document_name="alice.md",
            score=0.84,
            text="Alice follows the White Rabbit into the rabbit-hole.",
            section_title="White Rabbit",
            heading_path=("Characters", "White Rabbit"),
        ),
    ]

    selected = select_context_chunks_for_answer(
        chunks,
        question="White Rabbit 和 Alice 的情节关系是什么？",
        max_chunks=2,
        max_total_chars=4000,
        max_chunks_per_document=2,
    )

    assert "1:2" in {item.chunk_id for item in selected}


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
    assert "Answer Policy Contract:" in generator.last_prompt.system_prompt
    assert "External knowledge allowed: false." in generator.last_prompt.system_prompt
    assert "Allowed evidence markers: [S1]." in generator.last_prompt.system_prompt
    assert "Do not use model memory or external knowledge" in generator.last_prompt.system_prompt
    evidence_block = generator.last_prompt.user_prompt.split("Evidence Units:\n", maxsplit=1)[1]
    assert "乌萨奇长啥样？" not in evidence_block
    assert "明黄色的小兔子" not in evidence_block
    assert "user_id" not in generator.last_prompt.rendered_prompt
    assert "knowledge_base_id" not in generator.last_prompt.rendered_prompt
    assert "trace_id" not in generator.last_prompt.rendered_prompt
    assert "api_key" not in generator.last_prompt.rendered_prompt


def test_answer_question_does_not_treat_history_as_evidence_without_current_support() -> None:
    generator = CapturingAnswerGenerator("乌萨奇叫乌萨奇 [S1]。")
    result = answer_question(
        question="那它叫什么名字？",
        retrieved_chunks=[],
        conversation_context=[
            MessageContext(role="user", content="乌萨奇长啥样？"),
            MessageContext(role="assistant", content="乌萨奇叫乌萨奇 [S1]。"),
        ],
        generator=generator,
    )

    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []
    assert generator.call_count == 0
    assert result.answer_policy is not None
    assert result.answer_policy.outcome.value == "refuse"


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
            unit_text="乌萨奇外貌特征包括粉色内耳。",
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
                    text="乌萨奇外貌特征包括粉色内耳。",
                ),
            ],
            generator=StaticAnswerGenerator(
                "乌萨奇外貌特征包括粉色内耳 [S1]。它是蓝色兔子外型 [S2]。"
            ),
        )

    assert result.answer == "乌萨奇外貌特征包括粉色内耳 [S1]。它是蓝色兔子外型 [S2]。"
    assert [item.citation_marker for item in result.citations] == ["S1", "S2"]
    assert [item.snippet for item in result.citations] == [
        "乌萨奇外貌特征包括粉色内耳。",
        "乌萨奇是蓝色兔子外型。",
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


def test_answer_policy_passes_only_canonical_final_evidence_and_records_unknown_marker(
    session_factory: sessionmaker,
) -> None:
    generator = CapturingAnswerGenerator("Canonical fact [S1]. Invented [S99].")
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="policy.txt",
        )
        first_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Canonical fact is grounded.",
        )
        second_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="Broad parent chunk must not reach the provider.",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=first_chunk.chunk_key,
            unit_index=0,
            unit_text="Canonical fact is grounded.",
            metadata={"source_type": "text", "source_locator": "section:Canonical"},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=second_chunk.chunk_key,
            unit_index=1,
            unit_text="Unselected private evidence.",
            metadata={"source_type": "text", "source_locator": "section:Private"},
        )
        db.commit()
        retrieved = [
            _retrieved_chunk(
                chunk_id=first_chunk.chunk_key,
                chunk_db_id=first_chunk.id,
                document_id=document.id,
                document_name=document.original_filename,
                score=0.95,
                text=first_chunk.chunk_text,
            ),
            _retrieved_chunk(
                chunk_id=second_chunk.chunk_key,
                chunk_db_id=second_chunk.id,
                document_id=document.id,
                document_name=document.original_filename,
                score=0.90,
                text=second_chunk.chunk_text,
            ),
        ]
        all_candidates = build_citation_ready_fallback_units(
            question="What is the canonical fact?",
            retrieved_chunks=retrieved,
            chunk_units=load_citation_units_for_chunks(db=db, chunks=retrieved),
        )
        selected_candidate = next(
            item for item in all_candidates if item.chunk_id == first_chunk.chunk_key
        )
        final_evidences = build_evidences([selected_candidate])
        retrieval_result = RetrievalResult(
            query="What is the canonical fact?",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=final_evidences,
            context_text="canonical final context",
            trace_id=None,
            metadata={
                "context_chunks": retrieved,
                "evidence_units": all_candidates,
            },
        )
        trace = RetrievalTrace(
            user_id=user.id,
            knowledge_base_id=knowledge_base.id,
            query="What is the canonical fact?",
            mode=RetrievalMode.CHUNK_ONLY.value,
            top_k=2,
        )
        db.add(trace)
        db.flush()
        retrieval_result.trace_id = trace.id

        result = answer_question(
            db=db,
            question="What is the canonical fact?",
            retrieved_chunks=[],
            retrieval_result=retrieval_result,
            generator=generator,
        )
        db.refresh(trace)
        trace_metadata = json.loads(trace.metadata_json or "{}")

    assert generator.call_count == 1
    assert generator.last_evidence_units == [selected_candidate]
    assert "Broad parent chunk" not in generator.last_prompt.user_prompt
    assert "Unselected private evidence" not in generator.last_prompt.user_prompt
    assert result.answer == "Canonical fact [S1]. Invented ."
    assert [item.citation_marker for item in result.citations] == ["S1"]
    assert result.answer_policy is not None
    assert result.answer_policy.outcome.value == "answer"
    assert retrieval_result.metadata["answer_provider_called"] is True
    assert retrieval_result.metadata["answer_allowed_markers"] == ["S1"]
    assert retrieval_result.metadata["answer_unknown_markers_removed"] == 1
    assert trace_metadata["answer_policy_outcome"] == "answer"
    assert trace_metadata["answer_provider_called"] is True
    assert trace_metadata["answer_unknown_markers_removed"] == 1


def test_answer_policy_records_provider_exception_without_fabricating_result(
    session_factory: sessionmaker,
) -> None:
    generator = RaisingAnswerGenerator()
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="provider-error.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Provider error fact is grounded.",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Provider error fact is grounded.",
            metadata={"source_type": "text", "source_locator": "section:Provider"},
        )
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.95,
            text=chunk.chunk_text,
        )
        candidates = build_citation_ready_fallback_units(
            question="What is the provider error fact?",
            retrieved_chunks=[retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
        )
        retrieval_result = RetrievalResult(
            query="What is the provider error fact?",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=build_evidences(candidates),
            context_text="provider error final context",
            metadata={"context_chunks": [retrieved], "evidence_units": candidates},
        )

        with pytest.raises(RuntimeError, match="provider failed"):
            answer_question(
                db=db,
                question="What is the provider error fact?",
                retrieved_chunks=[],
                retrieval_result=retrieval_result,
                generator=generator,
            )

    assert generator.call_count == 1
    assert retrieval_result.metadata["answer_provider_called"] is True
    assert retrieval_result.metadata["answer_policy_outcome"] == "answer"


def test_heuristic_provider_uses_only_supplied_final_evidence_markers() -> None:
    evidence = type(
        "Evidence",
        (),
        {"text": "RETRIEVAL_MIN_SCORE defaults to 0.15.", "marker": "S1"},
    )()

    answer = HeuristicAnswerGenerator().generate(
        question="RETRIEVAL_MIN_SCORE 默认值是什么？",
        evidence_units=[evidence],
        prompt=None,  # type: ignore[arg-type]
    )

    assert answer == "根据当前知识库证据，RETRIEVAL_MIN_SCORE defaults to 0.15. [S1]"
    assert "S2" not in answer


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


def test_citation_ready_fallback_expands_persisted_units_with_unit_provenance(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="grounding.pdf",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="First grounded fact. Second grounded fact.",
        )
        first = _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="First grounded fact.",
            start_char=100,
            end_char=120,
            metadata={
                "source_type": "pdf",
                "page_number": 3,
                "source_locator": "page:3",
                "section_title": "Unit Section",
                "heading_path": ["Report", "Unit Section"],
            },
        )
        second = _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="Second grounded fact.",
            start_char=121,
            end_char=142,
            metadata={"source_type": "pdf", "page_number": 3, "source_locator": "page:3"},
        )
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
            source_type="pdf",
            char_start=90,
            char_end=150,
            page_number=9,
            source_locator="page:9",
        )
        units = load_citation_units_for_chunks(db=db, chunks=[retrieved])

        candidates = build_citation_ready_fallback_units(
            question="What are the grounded facts?",
            retrieved_chunks=[retrieved, retrieved],
            chunk_units=units,
        )

    assert [item.citation_unit_id for item in candidates] == [first.id, second.id]
    assert [item.marker for item in candidates] == ["S1", "S2"]
    assert candidates[0].source_locator == "page:3"
    assert candidates[0].page_number == 3
    assert (candidates[0].char_start, candidates[0].char_end) == (100, 120)
    assert candidates[0].section_title == "Unit Section"
    assert candidates[0].heading_path == ("Report", "Unit Section")


def test_citation_ready_fallback_keeps_chunk_without_units_non_ready() -> None:
    chunk = _retrieved_chunk(
        chunk_id="1:0",
        chunk_db_id=10,
        document_id=1,
        document_name="legacy.txt",
        score=0.8,
        text="Legacy chunk without citation units.",
    )

    candidates = build_citation_ready_fallback_units(
        question="What does the legacy document say?",
        retrieved_chunks=[chunk],
        chunk_units={},
    )

    assert len(candidates) == 1
    assert candidates[0].citation_unit_id is None
    assert candidates[0].citation_id is None
    assert candidates[0].text == chunk.text


def test_citation_ready_fallback_bounds_one_hundred_units_and_keeps_relevant_unit(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="configuration.md",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Configuration reference with many persisted facts.",
        )
        expected = None
        for unit_index in range(100):
            unit_text = f"Archived migration note {unit_index}."
            if unit_index == 73:
                unit_text = "RETRIEVAL_MIN_SCORE default value is 0.15."
            unit = _create_citation_unit(
                db,
                document=document,
                chunk_key=chunk.chunk_key,
                unit_index=unit_index,
                unit_text=unit_text,
                metadata={"source_type": "text", "source_locator": "section:Configuration"},
            )
            if unit_index == 73:
                expected = unit
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )

        candidates = build_citation_ready_fallback_units(
            question="RETRIEVAL_MIN_SCORE 的默认值是多少？",
            retrieved_chunks=[retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
            max_evidence_units=8,
        )

    assert expected is not None
    assert len(candidates) == 2
    assert expected.id in {item.citation_unit_id for item in candidates}
    assert [item.marker for item in candidates] == ["S1", "S2"]


def test_citation_ready_fallback_applies_global_limit_and_preserves_context_chunk_order(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="ordered.txt",
        )
        chunks = [
            _create_chunk(
                db,
                document=document,
                chunk_index=chunk_index,
                chunk_text=f"Context chunk {chunk_index}.",
            )
            for chunk_index in range(4)
        ]
        for chunk in chunks:
            for unit_index in range(2):
                _create_citation_unit(
                    db,
                    document=document,
                    chunk_key=chunk.chunk_key,
                    unit_index=chunk.chunk_index * 2 + unit_index,
                    unit_text=f"Fact {chunk.chunk_index}-{unit_index}.",
                    metadata={
                        "source_type": "text",
                        "source_locator": f"section:Chunk-{chunk.chunk_index}",
                    },
                )
        db.commit()
        retrieved_by_index = {
            chunk.chunk_index: _retrieved_chunk(
                chunk_id=chunk.chunk_key,
                chunk_db_id=chunk.id,
                document_id=document.id,
                document_name=document.original_filename,
                score=0.9 - chunk.chunk_index * 0.01,
                text=chunk.chunk_text,
            )
            for chunk in chunks
        }
        context_chunks = [retrieved_by_index[2], retrieved_by_index[0], retrieved_by_index[1]]
        all_units = load_citation_units_for_chunks(
            db=db,
            chunks=[*context_chunks, retrieved_by_index[3]],
        )

        candidates = build_citation_ready_fallback_units(
            question="List the context facts.",
            retrieved_chunks=context_chunks,
            chunk_units=all_units,
            max_evidence_units=5,
        )

    assert len(candidates) == 5
    assert [item.chunk_id for item in candidates] == [
        chunks[2].chunk_key,
        chunks[0].chunk_key,
        chunks[0].chunk_key,
        chunks[1].chunk_key,
        chunks[1].chunk_key,
    ]
    assert all(item.chunk_id != chunks[3].chunk_key for item in candidates)


def test_citation_ready_fallback_deduplicates_same_chunk_text(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="duplicates.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Duplicate and distinct grounded facts.",
        )
        for unit_index, unit_text in enumerate(
            ("Same grounded fact.", "  same   grounded fact. ", "Distinct grounded fact.")
        ):
            _create_citation_unit(
                db,
                document=document,
                chunk_key=chunk.chunk_key,
                unit_index=unit_index,
                unit_text=unit_text,
                metadata={"source_type": "text", "source_locator": "section:Facts"},
            )
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )

        candidates = build_citation_ready_fallback_units(
            question="What are the grounded facts?",
            retrieved_chunks=[retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
            max_units_per_chunk=3,
        )

    assert len(candidates) == 2
    assert {" ".join(item.text.split()).casefold() for item in candidates} == {
        "same grounded fact.",
        "distinct grounded fact.",
    }


def test_citation_ready_fallback_does_not_use_broad_parent_chunk_for_entity_match(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="catalog.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Aurora Pro catalog details. 重量：2.1 kg。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="重量：2.1 kg。",
            metadata={"source_type": "text", "source_locator": "section:Specifications"},
        )
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )

        candidates = build_citation_ready_fallback_units(
            question="Aurora Pro 重量是多少？",
            retrieved_chunks=[retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
        )

    assert len(candidates) == 1
    assert candidates[0].entity_exact_match is False
    assert candidates[0].entity_context_match is False


def test_citation_ready_fallback_bounds_serialized_prompt_context(
    session_factory: sessionmaker,
) -> None:
    context_budget = 220
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="budget.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Prompt context budget facts.",
        )
        for unit_index in range(4):
            _create_citation_unit(
                db,
                document=document,
                chunk_key=chunk.chunk_key,
                unit_index=unit_index,
                unit_text=f"Fact {unit_index}: " + "bounded context " * 6,
                metadata={"source_type": "text", "source_locator": "section:Budget"},
            )
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )

        candidates = build_citation_ready_fallback_units(
            question="What are the budget facts?",
            retrieved_chunks=[retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
            max_evidence_units=4,
            max_units_per_chunk=4,
            max_total_chars=context_budget,
        )

    prompt = build_fact_prompt(question="What are the budget facts?", evidence_units=candidates)
    evidence_context = prompt.user_prompt.split("Evidence Units:\n", maxsplit=1)[1]
    assert candidates
    assert len(candidates) < 4
    assert len(evidence_context) <= context_budget


def test_answer_citation_uses_the_same_unit_as_final_retrieval_evidence(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="canonical.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Canonical citation fact.",
        )
        unit = _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Canonical citation fact.",
            start_char=10,
            end_char=34,
            metadata={
                "source_type": "text",
                "source_locator": "chars:10-34",
                "section_title": "Canonical facts",
                "heading_path": ["Runbook", "Canonical facts"],
            },
        )
        db.commit()
        retrieved = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        candidates = build_citation_ready_fallback_units(
            question="What is the canonical citation fact?",
            retrieved_chunks=[retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved]),
        )
        evidences = [
            item.model_copy(
                update={
                    "final_score": 0.77,
                    "metadata": {
                        **item.metadata,
                        "retrieval_mode": RetrievalMode.HYBRID_TEXT.value,
                    },
                }
            )
            for item in build_evidences(candidates)
        ]
        retrieval_result = RetrievalResult(
            query="What is the canonical citation fact?",
            mode=RetrievalMode.HYBRID_TEXT,
            selected_mode=RetrievalMode.HYBRID_TEXT,
            effective_mode=RetrievalMode.HYBRID_TEXT,
            evidences=evidences,
            context_text="[S1]\ncontent: Canonical citation fact.",
            metadata={"context_chunks": [retrieved], "evidence_units": candidates},
        )

        answer = answer_question(
            db=db,
            question="What is the canonical citation fact?",
            retrieved_chunks=[],
            retrieval_result=retrieval_result,
            generator=StaticAnswerGenerator("Canonical citation fact [S1]."),
        )

    assert len(answer.citations) == 1
    assert answer.citations[0].text == evidences[0].text
    assert answer.citations[0].citation_unit_id == unit.id
    assert answer.citations[0].source_locator is not None
    assert answer.citations[0].source_locator.source_locator_text == "chars:10-34"
    assert answer.citations[0].citation_marker == "S1"
    assert answer.citations[0].heading_path == ["Runbook", "Canonical facts"]
    assert answer.citations[0].section_title == "Canonical facts"
    assert answer.citations[0].char_start == 10
    assert answer.citations[0].char_end == 34
    assert answer.citations[0].citation_ready is True
    assert answer.citations[0].retrieval_mode == "hybrid_text"
    assert answer.citations[0].score == 0.77


def test_citation_contract_normalizes_missing_locator_heading_and_invalid_char_range() -> None:
    citation = CitationRead(
        chunk_id="1:0",
        document_id=1,
        knowledge_base_id=1,
        scope="personal",
        team_id=None,
        document_name="legacy.txt",
        text="Legacy final evidence.",
        citation_unit_id=1,
        source_locator=None,
        heading_path=None,
        char_start=10,
        char_end=None,
    )

    assert citation.source_locator is None
    assert citation.heading_path == []
    assert citation.char_start is None
    assert citation.char_end is None
    assert citation.citation_ready is False
    assert citation.retrieval_mode is None
    assert citation.score is None


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
    assert len(evidence_units) == 1
    assert "除草检定" not in evidence_units[0].text


def test_select_evidence_units_entity_definition_filters_same_chunk_noise(
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
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text=(
                "乌萨奇是漫画《Chiikawa》中的核心主角。"
                "### 四、为什么这么火？乌萨奇完美契合不内耗人设。"
                "乌萨奇的生日是1月22日，声优是小泽亚李。"
            ),
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="乌萨奇是漫画《Chiikawa》中的核心主角。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="### 四、为什么这么火？乌萨奇完美契合不内耗人设。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=2,
            unit_text="乌萨奇的生日是1月22日，声优是小泽亚李。",
        )
        db.commit()

        evidence_units = select_evidence_units(
            question="乌萨奇是谁",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=chunk.id,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.93,
                    text=chunk.chunk_text,
                )
            ],
            chunk_units=load_citation_units_for_chunks(
                db=db,
                chunks=[
                    _retrieved_chunk(
                        chunk_id=chunk.chunk_key,
                        chunk_db_id=chunk.id,
                        document_id=document.id,
                        document_name=document.original_filename,
                        score=0.93,
                        text=chunk.chunk_text,
                    )
                ],
            ),
            max_evidence_units=4,
        )

    assert len(evidence_units) == 1
    assert evidence_units[0].citation_unit_id is not None
    assert "核心主角" in evidence_units[0].text
    assert "为什么这么火" not in evidence_units[0].text
    assert "声优" not in evidence_units[0].text


def test_select_evidence_units_entity_attribute_prefers_appearance_over_identity_and_birthday(
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
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="乌萨奇是核心主角。乌萨奇外貌：通体明黄色，有粉色内耳和白色尾巴。乌萨奇生日是1月22日。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="乌萨奇是核心主角。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="乌萨奇外貌：通体明黄色，有粉色内耳和白色尾巴。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=2,
            unit_text="乌萨奇生日是1月22日。",
        )
        db.commit()

        evidence_units = select_evidence_units(
            question="乌萨奇长什么样",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=chunk.id,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.9,
                    text=chunk.chunk_text,
                )
            ],
            chunk_units=load_citation_units_for_chunks(
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
            ),
            max_evidence_units=4,
        )

    assert evidence_units[0].text == "乌萨奇外貌：通体明黄色，有粉色内耳和白色尾巴。"


def test_select_evidence_units_entity_attribute_uses_chunk_context_for_unit_without_entity(
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
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text=(
                "一、基本设定\n中文名：乌萨奇\n"
                "外貌：通体明黄色的小兔子，有一对粉色内耳、圆眼睛、白色蓬松的棉花糖尾巴。\n"
                "生日：2019年1月22日\n声优：小泽亚李"
            ),
            metadata={"section_title": "一、基本设定", "heading_path": ["一、基本设定"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="中文名：乌萨奇",
            metadata={"section_title": "一、基本设定", "heading_path": ["一、基本设定"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="外貌：通体明黄色的小兔子，有一对粉色内耳、圆眼睛、白色蓬松的棉花糖尾巴。",
            metadata={"section_title": "一、基本设定", "heading_path": ["一、基本设定"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=2,
            unit_text="生日：2019年1月22日",
            metadata={"section_title": "一、基本设定", "heading_path": ["一、基本设定"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=3,
            unit_text="声优：小泽亚李",
            metadata={"section_title": "一、基本设定", "heading_path": ["一、基本设定"]},
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
            section_title="一、基本设定",
            heading_path=("一、基本设定",),
        )
        evidence_units = select_evidence_units(
            question="乌萨奇长什么样",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(
                db=db,
                chunks=[retrieved_chunk],
            ),
            max_evidence_units=4,
        )

    assert evidence_units
    assert evidence_units[0].text == "外貌：通体明黄色的小兔子，有一对粉色内耳、圆眼睛、白色蓬松的棉花糖尾巴。"
    assert evidence_units[0].entity_context_match is True
    assert all("生日" not in item.text for item in evidence_units)
    assert all("声优" not in item.text for item in evidence_units)


def test_select_evidence_units_entity_reason_prefers_reason_over_birthday(
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
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="乌萨奇生日是1月22日。乌萨奇受欢迎的原因是不内耗、反差萌和性格强大。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="乌萨奇生日是1月22日，声优是小泽亚李。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="乌萨奇受欢迎的原因是不内耗、反差萌和性格强大。",
        )
        db.commit()

        evidence_units = select_evidence_units(
            question="乌萨奇为什么受欢迎",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=chunk.id,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.9,
                    text=chunk.chunk_text,
                )
            ],
            chunk_units=load_citation_units_for_chunks(
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
            ),
            max_evidence_units=4,
        )

    assert "不内耗" in evidence_units[0].text
    assert "声优" not in evidence_units[0].text


def test_select_evidence_units_entity_reason_uses_chunk_context_for_unit_without_entity(
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
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text=(
                "乌萨奇为什么受欢迎\n乌萨奇的人设很突出。\n"
                "这种“疯批外表+暖男内心+超强战力”的极致反差，让它人气很高。"
            ),
            metadata={"section_title": "四、为什么这么火？"},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="乌萨奇的人设很突出。",
            metadata={"section_title": "四、为什么这么火？"},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="这种“疯批外表+暖男内心+超强战力”的极致反差，让它人气很高。",
            metadata={"section_title": "四、为什么这么火？"},
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
            section_title="四、为什么这么火？",
        )
        evidence_units = select_evidence_units(
            question="乌萨奇为什么受欢迎",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert evidence_units
    assert "反差" in evidence_units[0].text
    assert evidence_units[0].entity_context_match is True


def test_select_evidence_units_relation_allows_multiple_units_from_same_chunk(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="乌萨奇关系.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="乌萨奇和吉伊卡哇是朋友。乌萨奇和吉伊卡哇是伙伴。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="乌萨奇和吉伊卡哇是朋友。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="乌萨奇和吉伊卡哇是伙伴。",
        )
        db.commit()

        evidence_units = select_evidence_units(
            question="乌萨奇和吉伊卡哇是什么关系",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=chunk.id,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.9,
                    text=chunk.chunk_text,
                )
            ],
            chunk_units=load_citation_units_for_chunks(
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
            ),
            max_evidence_units=4,
        )

    assert len(evidence_units) == 2
    assert all("吉伊卡哇" in item.text for item in evidence_units)


def test_select_evidence_units_relation_does_not_use_contextual_entity_shortcut(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="乌萨奇关系.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="乌萨奇和吉伊卡哇是朋友。朋友。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="乌萨奇和吉伊卡哇是朋友。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="朋友。",
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="乌萨奇和吉伊卡哇是什么关系",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert [item.text for item in evidence_units] == ["乌萨奇和吉伊卡哇是朋友。"]


def test_select_evidence_units_relation_friend_has_positive_intent_alignment(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="team-relations.md",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Alice 和 Bob 是朋友。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Alice 和 Bob 是朋友。",
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="Alice 和 Bob 是什么关系？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert [item.text for item in evidence_units] == ["Alice 和 Bob 是朋友。"]
    assert evidence_units[0].intent_alignment > 0
    assert evidence_units[0].entity_exact_match is True
    assert evidence_units[0].entity_context_match is False


def test_select_evidence_units_relation_partner_is_supported(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="partners.md",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Aurora Labs 是 Nova Systems 的合作伙伴。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Aurora Labs 是 Nova Systems 的合作伙伴。",
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="Aurora Labs 和 Nova Systems 是什么关系？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert [item.text for item in evidence_units] == ["Aurora Labs 是 Nova Systems 的合作伙伴。"]
    assert evidence_units[0].intent_alignment > 0
    assert evidence_units[0].entity_exact_match is True
    assert evidence_units[0].entity_context_match is False


def test_select_evidence_units_relation_ignores_together_without_relation_intent(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="meeting-notes.md",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Alice 和 Bob 一起参加了会议。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Alice 和 Bob 一起参加了会议。",
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="Alice 和 Bob 是什么关系？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert evidence_units == []


def test_select_evidence_units_entity_attribute_rejects_unrelated_document_context(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="其它角色.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="角色外貌设定：通体明黄色，有粉色内耳和白色尾巴。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="外貌：通体明黄色，有粉色内耳和白色尾巴。",
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="乌萨奇长什么样",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert evidence_units == []


def test_select_evidence_units_team_member_attribute_uses_matching_heading_only(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="team.md",
        )
        chunk_text = (
            "# Team\n\n"
            "## Alice Chen\n角色：检索工程师\n办公地点：Singapore\n\n"
            "## Bob Li\n角色：平台工程师\n办公地点：Shanghai\n\n"
            "## Carol Wang\n角色：产品经理\n办公地点：Beijing"
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text=chunk_text,
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="办公地点：Singapore",
            metadata={"section_title": "Alice Chen", "heading_path": ["Team", "Alice Chen"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="办公地点：Shanghai",
            metadata={"section_title": "Bob Li", "heading_path": ["Team", "Bob Li"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=2,
            unit_text="办公地点：Beijing",
            metadata={"section_title": "Carol Wang", "heading_path": ["Team", "Carol Wang"]},
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        chunk_units = load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk])

        alice_evidence = select_evidence_units(
            question="Alice Chen 的办公地点在哪里？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=chunk_units,
            max_evidence_units=4,
        )
        bob_evidence = select_evidence_units(
            question="Bob Li 的办公地点在哪里？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=chunk_units,
            max_evidence_units=4,
        )

    assert [item.text for item in alice_evidence] == ["办公地点：Singapore"]
    assert alice_evidence[0].entity_context_match is True
    assert [item.text for item in bob_evidence] == ["办公地点：Shanghai"]
    assert bob_evidence[0].entity_context_match is True


def test_select_evidence_units_product_attribute_does_not_cross_entities(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="products.md",
        )
        chunk_text = (
            "## Aurora Mini\n颜色：银色\n重量：1.2 kg\n特点：便携\n\n"
            "## Aurora Pro\n颜色：黑色\n重量：2.1 kg\n特点：高性能\n\n"
            "## Aurora Air\n颜色：蓝色\n重量：0.9 kg\n特点：轻薄"
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text=chunk_text,
        )
        unit_specs = [
            ("颜色：银色", "Aurora Mini"),
            ("重量：1.2 kg", "Aurora Mini"),
            ("颜色：黑色", "Aurora Pro"),
            ("重量：2.1 kg", "Aurora Pro"),
            ("颜色：蓝色", "Aurora Air"),
            ("重量：0.9 kg", "Aurora Air"),
        ]
        for index, (unit_text, product_name) in enumerate(unit_specs):
            _create_citation_unit(
                db,
                document=document,
                chunk_key=chunk.chunk_key,
                unit_index=index,
                unit_text=unit_text,
                metadata={"section_title": product_name, "heading_path": [product_name]},
            )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        chunk_units = load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk])

        mini_color = select_evidence_units(
            question="Aurora Mini 颜色是什么？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=chunk_units,
            max_evidence_units=4,
        )
        pro_weight = select_evidence_units(
            question="Aurora Pro 重量是多少？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=chunk_units,
            max_evidence_units=4,
        )

    assert [item.text for item in mini_color] == ["颜色：银色"]
    assert "黑色" not in mini_color[0].text
    assert "蓝色" not in mini_color[0].text
    assert [item.text for item in pro_weight] == ["重量：2.1 kg"]
    assert "1.2 kg" not in pro_weight[0].text
    assert "0.9 kg" not in pro_weight[0].text


def test_select_evidence_units_context_requires_local_entity_anchor(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="team.md",
        )
        chunk_text = (
            "## Alice Chen\n角色：检索工程师\n办公地点：Singapore\n\n"
            "## Bob Li\n办公地点：Shanghai"
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text=chunk_text,
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="办公地点：Shanghai",
            metadata={"section_title": "Bob Li", "heading_path": ["Bob Li"]},
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="Alice Chen 的办公地点在哪里？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert evidence_units == []


def test_select_evidence_units_accepted_limit_skips_duplicate_without_counting_it(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="team.md",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="# Team\n\n## Alice Chen\n办公地点：Singapore\n位置：Singapore Office",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="办公地点：Singapore",
            metadata={"section_title": "Alice Chen", "heading_path": ["Team", "Alice Chen"]},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="位置：Singapore Office",
            metadata={"section_title": "Alice Chen", "heading_path": ["Team", "Alice Chen"]},
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="Alice Chen 的办公地点在哪里？",
            retrieved_chunks=[retrieved_chunk, retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert [item.text for item in evidence_units] == ["办公地点：Singapore", "位置：Singapore Office"]


def test_select_evidence_units_max_evidence_units_stops_global_selection(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="systems.md",
        )
        first_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="PureLink 是一个知识库问答系统。",
        )
        second_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="PureLink 也提供文档检索工具。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=first_chunk.chunk_key,
            unit_index=0,
            unit_text="PureLink 是一个知识库问答系统。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=second_chunk.chunk_key,
            unit_index=1,
            unit_text="PureLink 也提供文档检索工具。",
        )
        db.commit()

        first_retrieved = _retrieved_chunk(
            chunk_id=first_chunk.chunk_key,
            chunk_db_id=first_chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.95,
            text=first_chunk.chunk_text,
        )
        second_retrieved = _retrieved_chunk(
            chunk_id=second_chunk.chunk_key,
            chunk_db_id=second_chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=second_chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="PureLink 是什么？",
            retrieved_chunks=[first_retrieved, second_retrieved],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[first_retrieved, second_retrieved]),
            max_evidence_units=1,
        )

    assert [item.text for item in evidence_units] == ["PureLink 是一个知识库问答系统。"]


def test_select_evidence_units_pairs_technical_identifier_with_default_value(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="retrieval-config.md",
        )
        role_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="RETRIEVAL_MIN_SCORE controls minimum-score filtering.",
        )
        value_chunk = _create_chunk(
            db,
            document=document,
            chunk_index=1,
            chunk_text="## Retrieval Min Score\nDefault value: 0.15.",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=role_chunk.chunk_key,
            unit_index=0,
            unit_text="RETRIEVAL_MIN_SCORE controls minimum-score filtering.",
            metadata={"section_title": "Retrieval configuration"},
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=value_chunk.chunk_key,
            unit_index=1,
            unit_text="Default value: 0.15.",
            metadata={
                "section_title": "Retrieval Min Score",
                "heading_path": ["Configuration", "Retrieval Min Score"],
            },
        )
        db.commit()

        role_result = _retrieved_chunk(
            chunk_id=role_chunk.chunk_key,
            chunk_db_id=role_chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.95,
            text=role_chunk.chunk_text,
            section_title="Retrieval configuration",
        )
        value_result = _retrieved_chunk(
            chunk_id=value_chunk.chunk_key,
            chunk_db_id=value_chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.88,
            text=value_chunk.chunk_text,
            section_title="Retrieval Min Score",
            heading_path=("Configuration", "Retrieval Min Score"),
        )
        evidence_units = select_evidence_units(
            question="RETRIEVAL_MIN_SCORE 默认值是什么？",
            retrieved_chunks=[role_result, value_result],
            chunk_units=load_citation_units_for_chunks(
                db=db,
                chunks=[role_result, value_result],
            ),
            max_evidence_units=1,
        )

    assert [item.text for item in evidence_units] == ["Default value: 0.15."]


def test_select_evidence_units_mixed_english_entity_config_attribute(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="providers.md",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="## DeepSeek API\n配置：DEEPSEEK_API_KEY\n规格：OpenAI-compatible chat endpoint",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="配置：DEEPSEEK_API_KEY",
            metadata={"section_title": "DeepSeek API", "heading_path": ["DeepSeek API"]},
        )
        db.commit()

        retrieved_chunk = _retrieved_chunk(
            chunk_id=chunk.chunk_key,
            chunk_db_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            score=0.9,
            text=chunk.chunk_text,
        )
        evidence_units = select_evidence_units(
            question="DeepSeek API 的配置在哪里？",
            retrieved_chunks=[retrieved_chunk],
            chunk_units=load_citation_units_for_chunks(db=db, chunks=[retrieved_chunk]),
            max_evidence_units=4,
        )

    assert [item.text for item in evidence_units] == ["配置：DEEPSEEK_API_KEY"]


def test_select_evidence_units_generic_factual_keeps_existing_multi_unit_behavior(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        user, knowledge_base = _create_user_and_kb(db)
        document = _create_document(
            db,
            user=user,
            knowledge_base=knowledge_base,
            original_filename="tasks.txt",
        )
        chunk = _create_chunk(
            db,
            document=document,
            chunk_index=0,
            chunk_text="Redis 触发任务。ProcessingJob 保存任务状态。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Redis 触发任务。",
        )
        _create_citation_unit(
            db,
            document=document,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="ProcessingJob 保存任务状态。",
        )
        db.commit()

        evidence_units = select_evidence_units(
            question="任务处理如何记录状态",
            retrieved_chunks=[
                _retrieved_chunk(
                    chunk_id=chunk.chunk_key,
                    chunk_db_id=chunk.id,
                    document_id=document.id,
                    document_name=document.original_filename,
                    score=0.9,
                    text=chunk.chunk_text,
                )
            ],
            chunk_units=load_citation_units_for_chunks(
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
            ),
            max_evidence_units=4,
        )

    assert len(evidence_units) == 2


def test_select_evidence_units_overview_can_disable_entity_specific_gate() -> None:
    retrieved_chunks = [
        _retrieved_chunk(
            chunk_id="1:0",
            document_id=1,
            document_name="overview.txt",
            score=0.9,
            text="乌萨奇是核心主角。",
        ),
        _retrieved_chunk(
            chunk_id="1:1",
            document_id=1,
            document_name="overview.txt",
            score=0.89,
            text="生日和声优等资料也在知识库中。",
        ),
    ]

    evidence_units = select_evidence_units(
        question="总结乌萨奇是谁",
        retrieved_chunks=retrieved_chunks,
        chunk_units={},
        max_evidence_units=4,
        use_query_evidence_profile=False,
    )

    assert len(evidence_units) == 2


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


def test_answer_question_refuses_chunk_fallback_when_citation_units_are_missing() -> None:
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

    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []
    assert result.answer_policy is not None
    assert result.answer_policy.reason == "no_citation_ready_evidence"


def test_answer_question_does_not_fabricate_sentence_citation_for_chunk_fallback() -> None:
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

    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []
    assert result.answer_policy is not None
    assert result.answer_policy.reason == "no_citation_ready_evidence"
