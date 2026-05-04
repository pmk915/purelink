from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.document_processing import (
    filter_generated_citation_units,
    GeneratedCitationUnitPayload,
    GeneratedChunkPayload,
    build_citation_units_for_chunk,
    expand_sentence_spans_for_citation_units,
    parse_chunk_metadata_json,
    process_document,
    split_text_into_sentence_spans,
    validate_generated_citation_units,
)


load_all_models()


@pytest.fixture
def session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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


def _create_document(db, *, original_filename: str, storage_path: str) -> Document:
    user = User(
        email=f"{original_filename}@example.com",
        username=original_filename.replace(".", "-"),
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()

    kb = KnowledgeBase(
        name="Citation KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(kb)
    db.flush()

    document = Document(
        knowledge_base_id=kb.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename=original_filename,
        original_filename=original_filename,
        file_type="text/plain",
        file_size=128,
        storage_path=storage_path,
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    db.add(document)
    db.flush()
    return document


def test_split_text_into_sentence_spans_supports_chinese_and_english() -> None:
    spans = split_text_into_sentence_spans(
        "PureLink keeps Redis lightweight. ProcessingJob stores task facts。Worker retries failed jobs！"
    )

    assert [item.text for item in spans] == [
        "PureLink keeps Redis lightweight.",
        "ProcessingJob stores task facts。",
        "Worker retries failed jobs！",
    ]


def test_build_citation_units_generates_multiple_units_and_inherits_metadata() -> None:
    chunk = GeneratedChunkPayload(
        chunk_key="12:3",
        chunk_index=3,
        chunk_text=(
            "PureLink 将 ProcessingJob 持久化在 PostgreSQL。"
            "Redis 只负责触发 worker。"
            "Worker 启动时会恢复 queued job。"
        ),
        metadata_json=json.dumps(
            {
                "source_type": "docx",
                "section_title": "系统架构",
                "source_locator": "section:系统架构",
                "char_start": 120,
                "char_end": 180,
            },
            ensure_ascii=False,
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=20,
        target_chars=40,
        max_chars=120,
        max_sentences=2,
    )

    assert len(units) >= 2
    assert [item.unit_index for item in units] == list(range(len(units)))
    first_unit = units[0]
    first_metadata = json.loads(first_unit.metadata_json or "{}")
    assert first_unit.unit_text
    assert first_unit.start_char is not None
    assert first_unit.end_char is not None
    assert first_unit.start_char < first_unit.end_char
    assert first_metadata["source_type"] == "docx"
    assert first_metadata["section_title"] == "系统架构"
    assert first_metadata["parent_chunk_index"] == 3


def test_build_citation_units_merges_short_followup_sentence() -> None:
    chunk = GeneratedChunkPayload(
        chunk_key="1:0",
        chunk_index=0,
        chunk_text="Redis 只保存 job_id。这种方式提升可靠性。",
        metadata_json=json.dumps({"source_type": "text"}, ensure_ascii=False),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=16,
        target_chars=60,
        max_chars=120,
        max_sentences=3,
    )

    assert len(units) == 1
    assert units[0].unit_text == "Redis 只保存 job_id。 这种方式提升可靠性。"


def test_build_citation_units_preserves_pdf_page_metadata() -> None:
    chunk = GeneratedChunkPayload(
        chunk_key="9:1",
        chunk_index=1,
        chunk_text="Worker 会恢复 queued jobs，避免任务永久卡住。下一句仍然属于同一页。",
        metadata_json=json.dumps(
            {
                "source_type": "pdf",
                "page_number": 5,
                "source_locator": "page:5",
                "char_start": 300,
                "char_end": 360,
            },
            ensure_ascii=False,
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=20,
        target_chars=60,
        max_chars=120,
        max_sentences=2,
    )

    assert units
    metadata = json.loads(units[0].metadata_json or "{}")
    assert metadata["source_type"] == "pdf"
    assert metadata["page_number"] == 5
    assert metadata["source_locator"] == "page:5"


def test_build_citation_units_rebuilds_text_source_locator_to_unit_range() -> None:
    chunk = GeneratedChunkPayload(
        chunk_key="2:0",
        chunk_index=0,
        chunk_text="第一句说明 Redis 只负责触发。第二句说明 ProcessingJob 是事实来源。",
        metadata_json=json.dumps(
            {
                "source_type": "text",
                "source_locator": "chars:0-200",
                "char_start": 0,
                "char_end": 200,
            },
            ensure_ascii=False,
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=10,
        target_chars=20,
        max_chars=40,
        max_sentences=1,
    )

    assert len(units) >= 2
    first_metadata = json.loads(units[0].metadata_json or "{}")
    assert first_metadata["source_locator"] != "chars:0-200"
    assert first_metadata["source_locator"].startswith("chars:")
    assert units[0].start_char is not None
    assert units[0].end_char is not None
    assert first_metadata["source_locator"] == f"chars:{units[0].start_char}-{units[0].end_char}"


def test_expand_sentence_spans_for_citation_units_splits_oversized_sentence_on_clause_boundary() -> None:
    sentence_spans = split_text_into_sentence_spans(
        "乌萨奇通常有粉色内耳、圆眼睛、白色尾巴、蓝色兔子外型。"
    )

    expanded = expand_sentence_spans_for_citation_units(
        sentence_spans,
        max_chars=18,
    )

    assert len(expanded) >= 2
    assert all(item.text.endswith(("、", "。")) for item in expanded)


def test_validate_generated_citation_units_allows_short_but_meaningful_snippets() -> None:
    validate_generated_citation_units(
        [
            GeneratedCitationUnitPayload(
                chunk_key="1:0",
                unit_index=0,
                unit_text="架构",
                start_char=0,
                end_char=2,
                metadata_json=json.dumps({"source_type": "docx"}, ensure_ascii=False),
            )
        ]
    )


def test_filter_generated_citation_units_drops_invalid_units_without_failing() -> None:
    units = filter_generated_citation_units(
        citation_units=[
            GeneratedCitationUnitPayload(
                chunk_key="1:0",
                unit_index=0,
                unit_text="有效引用片段。",
                start_char=0,
                end_char=6,
                metadata_json=json.dumps({"source_type": "docx"}, ensure_ascii=False),
            ),
            GeneratedCitationUnitPayload(
                chunk_key="1:0",
                unit_index=1,
                unit_text="\x00\x00",
                start_char=7,
                end_char=9,
                metadata_json=json.dumps({"source_type": "docx"}, ensure_ascii=False),
            ),
        ],
        document_id=1,
        knowledge_base_id=1,
    )

    assert len(units) == 1
    assert units[0].unit_text == "有效引用片段。"


def test_document_chunk_and_citation_unit_have_parent_child_relationship(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        document = _create_document(
            db,
            original_filename="tree.txt",
            storage_path="tree.txt",
        )
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_key=f"{document.id}:0",
            chunk_index=0,
            chunk_text="Redis 只负责触发。",
        )
        db.add(chunk)
        db.flush()

        unit_a = DocumentCitationUnit(
            document_id=document.id,
            chunk_id=chunk.id,
            knowledge_base_id=document.knowledge_base_id,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Redis 只负责触发。",
        )
        unit_b = DocumentCitationUnit(
            document_id=document.id,
            chunk_id=chunk.id,
            knowledge_base_id=document.knowledge_base_id,
            chunk_key=chunk.chunk_key,
            unit_index=1,
            unit_text="ProcessingJob 记录事实来源。",
        )
        db.add_all([unit_a, unit_b])
        db.commit()
        db.refresh(chunk)
        db.refresh(unit_a)
        child_ids = [item.id for item in chunk.citation_units]
        parent_chunk_id = unit_a.chunk.id

    assert unit_a.chunk_id == chunk.id
    assert parent_chunk_id == chunk.id
    assert child_ids == [unit_a.id, unit_b.id]


def test_deleting_chunk_cascades_to_citation_units(
    session_factory: sessionmaker,
) -> None:
    with session_factory() as db:
        document = _create_document(
            db,
            original_filename="cascade.txt",
            storage_path="cascade.txt",
        )
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_key=f"{document.id}:0",
            chunk_index=0,
            chunk_text="Redis 只负责触发。",
        )
        db.add(chunk)
        db.flush()
        unit = DocumentCitationUnit(
            document_id=document.id,
            chunk_id=chunk.id,
            knowledge_base_id=document.knowledge_base_id,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text="Redis 只负责触发。",
        )
        db.add(unit)
        db.commit()

        db.delete(chunk)
        db.commit()

        remaining_units = list(
            db.scalars(
                select(DocumentCitationUnit).where(DocumentCitationUnit.document_id == document.id)
            )
        )

    assert remaining_units == []


def test_process_document_replaces_old_citation_units_idempotently(
    session_factory: sessionmaker,
    tmp_path: Path,
) -> None:
    upload_root = tmp_path / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)

    with session_factory() as db:
        document = _create_document(
            db,
            original_filename="notes.txt",
            storage_path="notes.txt",
        )
        source_path = upload_root / "notes.txt"
        source_path.write_text(
            "Redis 只保存 job_id。ProcessingJob 负责状态持久化。Worker 会恢复 queued job。",
            encoding="utf-8",
        )

        first_result = process_document(
            db,
            document=document,
            upload_root=upload_root,
        )
        db.commit()
        first_units = list(
            db.scalars(
                select(DocumentCitationUnit)
                .where(DocumentCitationUnit.document_id == document.id)
                .order_by(DocumentCitationUnit.unit_index.asc())
            )
        )

        source_path.write_text(
            "Redis 只负责触发。ProcessingJob 才是任务事实来源。Worker 会在启动时恢复 queued job。",
            encoding="utf-8",
        )
        second_result = process_document(
            db,
            document=document,
            upload_root=upload_root,
        )
        db.commit()
        second_units = list(
            db.scalars(
                select(DocumentCitationUnit)
                .where(DocumentCitationUnit.document_id == document.id)
                .order_by(DocumentCitationUnit.unit_index.asc())
            )
        )
        saved_chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        )
        chunk_lookup = {item.id: item for item in saved_chunks}

    assert first_result.chunk_count >= 1
    assert second_result.chunk_count >= 1
    assert first_units
    assert second_units
    assert all(item.created_at is not None for item in second_units)
    assert all(item.updated_at is not None for item in second_units)
    assert all(item.chunk_id in chunk_lookup for item in second_units)
    assert all(item.chunk_key == chunk_lookup[item.chunk_id].chunk_key for item in second_units)
    assert len({item.id for item in second_units}) == len(second_units)
    assert "任务事实来源" in " ".join(item.unit_text for item in second_units)
