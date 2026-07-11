from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.document_block import DocumentBlock
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentBlockType,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.document_chunking.types import ChunkSourceSpan
from app.services.document_processing import (
    filter_generated_citation_units,
    GeneratedCitationUnitPayload,
    GeneratedChunkPayload,
    build_extracted_text_result,
    build_citation_units_for_chunk,
    chunk_extracted_text_result,
    expand_sentence_spans_for_citation_units,
    parse_chunk_metadata_json,
    process_document,
    split_text_into_sentence_spans,
    validate_generated_citation_units,
)
from app.services.document_processing import ExtractedTextSegment
from app.services.source_locator import build_preview_target_for_chunk


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


def _create_document(
    db,
    *,
    original_filename: str,
    storage_path: str,
    file_type: str = "text/plain",
) -> Document:
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
        file_type=file_type,
        file_size=128,
        storage_path=storage_path,
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    db.add(document)
    db.flush()
    return document


def _set_chunk_strategy(monkeypatch: pytest.MonkeyPatch, strategy: str) -> None:
    monkeypatch.setenv("CHUNK_STRATEGY", strategy)
    get_settings.cache_clear()


def _metadata_json(payload: str | None) -> dict[str, object]:
    return json.loads(payload or "{}")


def _citation_preview_target(unit: DocumentCitationUnit):
    metadata = _metadata_json(unit.metadata_json)
    return build_preview_target_for_chunk(
        SimpleNamespace(
            document_id=unit.document_id,
            source_type=metadata.get("source_type"),
            source_locator=metadata.get("source_locator"),
            char_start=unit.start_char,
            char_end=unit.end_char,
            page_number=metadata.get("page_number"),
            start_time=metadata.get("start_time"),
            end_time=metadata.get("end_time"),
            section_title=metadata.get("section_title"),
            heading_path=metadata.get("heading_path"),
        )
    )


def _build_minimal_pdf(*, text: str) -> bytes:
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT\n/F1 12 Tf\n72 720 Td\n({escaped_text}) Tj\nET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n",
        (
            f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]
    return b"%PDF-1.4\n" + b"".join(objects) + b"%%EOF\n"


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


def test_fixed_chunking_generates_source_spans_for_prepared_segments() -> None:
    extracted = build_extracted_text_result(
        source_type="text",
        extractor="text",
        raw_segments=[
            ExtractedTextSegment(
                text="Page one text.",
                metadata={"source_type": "text", "section_title": "One", "extractor": "text"},
            ),
            ExtractedTextSegment(
                text="Page two text.",
                metadata={"source_type": "text", "section_title": "Two", "extractor": "text"},
            ),
        ],
    )

    chunks = chunk_extracted_text_result(
        extracted=extracted,
        document_id=7,
        chunk_size=200,
        direct_chunk_threshold=200,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_text == "Page one text.\n\nPage two text."
    assert [(span.local_start, span.local_end) for span in chunks[0].source_spans] == [
        (0, 14),
        (16, 30),
    ]
    assert [
        (span.source_char_start, span.source_char_end, span.section_title)
        for span in chunks[0].source_spans
    ] == [
        (0, 14, "One"),
        (16, 30, "Two"),
    ]


def test_boundary_aware_citation_units_keep_field_lines_separate() -> None:
    text = "乌萨奇是吉伊卡哇作品中的角色。\n生日：2019年1月22日\n声：小泽亚李"
    birthday_start = text.index("生日")
    voice_start = text.index("声：")
    chunk = GeneratedChunkPayload(
        chunk_key="3:0",
        chunk_index=0,
        chunk_text=text,
        metadata_json=json.dumps(
            {
                "source_type": "text",
                "char_start": 100,
                "char_end": 100 + len(text),
                "source_locator": f"chars:100-{100 + len(text)}",
            },
            ensure_ascii=False,
        ),
        source_spans=(
            ChunkSourceSpan(
                local_start=0,
                local_end=birthday_start - 1,
                source_char_start=100,
                source_char_end=100 + birthday_start - 1,
                block_type="text",
                source_type="text",
            ),
            ChunkSourceSpan(
                local_start=birthday_start,
                local_end=voice_start - 1,
                source_char_start=100 + birthday_start,
                source_char_end=100 + voice_start - 1,
                block_type="text",
                line_role="field",
                source_type="text",
            ),
            ChunkSourceSpan(
                local_start=voice_start,
                local_end=len(text),
                source_char_start=100 + voice_start,
                source_char_end=100 + len(text),
                block_type="text",
                line_role="field",
                source_type="text",
            ),
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=40,
        target_chars=80,
        max_chars=120,
        max_sentences=3,
    )

    unit_texts = [unit.unit_text for unit in units]
    assert "生日：2019年1月22日" in unit_texts
    assert "声：小泽亚李" in unit_texts
    assert not any("生日" in unit_text and "声：" in unit_text for unit_text in unit_texts)
    birthday_unit = units[unit_texts.index("生日：2019年1月22日")]
    birthday_metadata = json.loads(birthday_unit.metadata_json or "{}")
    assert birthday_unit.start_char == 100 + birthday_start
    assert birthday_metadata["source_locator"] == f"chars:{birthday_unit.start_char}-{birthday_unit.end_char}"
    assert birthday_metadata["line_role"] == "field"


def test_boundary_aware_citation_units_drop_heading_only_but_keep_short_field() -> None:
    text = "一、基本设定\n声优：小泽亚李"
    field_start = text.index("声优")
    chunk = GeneratedChunkPayload(
        chunk_key="3:1",
        chunk_index=1,
        chunk_text=text,
        metadata_json=json.dumps(
            {
                "source_type": "text",
                "char_start": 300,
                "char_end": 300 + len(text),
            },
            ensure_ascii=False,
        ),
        source_spans=(
            ChunkSourceSpan(
                local_start=0,
                local_end=field_start - 1,
                source_char_start=300,
                source_char_end=300 + field_start - 1,
                block_type="heading",
                source_type="text",
            ),
            ChunkSourceSpan(
                local_start=field_start,
                local_end=len(text),
                source_char_start=300 + field_start,
                source_char_end=300 + len(text),
                block_type="text",
                line_role="field",
                source_type="text",
            ),
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=40,
        target_chars=80,
        max_chars=120,
        max_sentences=3,
    )

    assert [unit.unit_text for unit in units] == ["声优：小泽亚李"]


def test_boundary_aware_citation_units_drop_common_pdf_section_heading() -> None:
    chunk = GeneratedChunkPayload(
        chunk_key="3:2",
        chunk_index=2,
        chunk_text="登场角色",
        metadata_json=json.dumps(
            {
                "source_type": "pdf",
                "page_number": 1,
                "char_start": 500,
                "char_end": 504,
            },
            ensure_ascii=False,
        ),
        source_spans=(
            ChunkSourceSpan(
                local_start=0,
                local_end=4,
                source_char_start=500,
                source_char_end=504,
                page_number=1,
                block_type="text",
                source_type="pdf",
            ),
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=40,
        target_chars=80,
        max_chars=120,
        max_sentences=3,
    )

    assert units == []


def test_boundary_aware_citation_units_preserve_pdf_visual_newlines() -> None:
    text = "兔兔（うさぎ）\n别名通常译作乌萨奇\n吉伊卡哇和小八是朋友。"
    chunk = GeneratedChunkPayload(
        chunk_key="4:0",
        chunk_index=0,
        chunk_text=text,
        metadata_json=json.dumps(
            {
                "source_type": "pdf",
                "page_number": 2,
                "char_start": 200,
                "char_end": 200 + len(text),
                "source_locator": "page:2",
            },
            ensure_ascii=False,
        ),
        source_spans=(
            ChunkSourceSpan(
                local_start=0,
                local_end=len(text),
                source_char_start=200,
                source_char_end=200 + len(text),
                page_number=2,
                block_type="text",
                extractor="pymupdf",
                source_type="pdf",
            ),
        ),
    )

    units = build_citation_units_for_chunk(
        chunk=chunk,
        chunk_metadata=parse_chunk_metadata_json(chunk.metadata_json),
        min_chars=10,
        target_chars=120,
        max_chars=200,
        max_sentences=3,
    )

    assert len(units) == 1
    assert units[0].unit_text == "兔兔（うさぎ） 别名通常译作乌萨奇 吉伊卡哇和小八是朋友。"
    metadata = json.loads(units[0].metadata_json or "{}")
    assert metadata["page_number"] == 2
    assert metadata["source_locator"] == "page:2"
    assert metadata["extractor"] == "pymupdf"


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


def test_markdown_like_txt_round_trip_persists_block_and_citation_metadata(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_chunk_strategy(monkeypatch, "fixed")
    source_text = (
        "乌萨奇（Usagi / うさぎ），是日本漫画家ナガノ创作的漫画《Chiikawa》中的核心主角之一。\n\n"
        "### 一、基本设定\n"
        "中文名：乌萨奇\n"
        "生日：2019年1月22日\n"
        "声优：小泽亚李\n"
        "外貌：明黄色的小兔子，有粉色内耳和白色尾巴。\n\n"
        "### 二、关系\n"
        "吉伊卡哇：朋友\n"
    )
    storage_path = "usagi-structured.txt"
    (tmp_path / storage_path).write_text(source_text, encoding="utf-8")

    with session_factory() as db:
        document = _create_document(
            db,
            original_filename=storage_path,
            storage_path=storage_path,
            file_type="text/plain",
        )
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
        units = list(
            db.scalars(
                select(DocumentCitationUnit)
                .where(DocumentCitationUnit.document_id == document_id)
                .order_by(DocumentCitationUnit.unit_index.asc())
            )
        )

    assert any(block.block_type == DocumentBlockType.HEADING for block in blocks)
    plain_text = "\n\n".join(block.text for block in blocks)
    for block in blocks:
        metadata = _metadata_json(block.metadata_json)
        assert metadata["source_type"] == "text"
        assert plain_text[metadata["char_start"]:metadata["char_end"]] == block.text

    relation_block = next(block for block in blocks if block.text == "吉伊卡哇：朋友")
    relation_metadata = _metadata_json(relation_block.metadata_json)
    assert relation_metadata["section_title"] == "二、关系"
    assert relation_metadata["heading_path"] == ["二、关系"]

    identity_unit = next(unit for unit in units if "核心主角" in unit.unit_text)
    assert "生日" not in identity_unit.unit_text
    assert "声优" not in identity_unit.unit_text
    assert "外貌" not in identity_unit.unit_text

    field_unit = next(unit for unit in units if unit.unit_text == "声优：小泽亚李")
    field_metadata = _metadata_json(field_unit.metadata_json)
    assert field_metadata["section_title"] == "一、基本设定"
    assert field_metadata["heading_path"] == ["一、基本设定"]
    assert field_metadata["char_start"] == field_unit.start_char
    assert field_metadata["char_end"] == field_unit.end_char
    assert field_metadata["source_locator"] == "section:一、基本设定"
    assert plain_text[field_unit.start_char:field_unit.end_char] == field_unit.unit_text


def test_block_aware_pdf_round_trip_persists_page_locator_and_extractor(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_chunk_strategy(monkeypatch, "block_aware")
    storage_path = "manual.pdf"
    (tmp_path / storage_path).write_bytes(
        _build_minimal_pdf(
            text=(
                "PureLink PDF manuals stay searchable. "
                "Citation units keep page metadata for preview."
            )
        )
    )

    with session_factory() as db:
        document = _create_document(
            db,
            original_filename=storage_path,
            storage_path=storage_path,
            file_type="application/pdf",
        )
        process_document(db, document=document, upload_root=tmp_path)
        db.commit()
        document_id = document.id

    with session_factory() as db:
        units = list(
            db.scalars(
                select(DocumentCitationUnit)
                .where(DocumentCitationUnit.document_id == document_id)
                .order_by(DocumentCitationUnit.unit_index.asc())
            )
        )

    assert units
    for unit in units:
        metadata = _metadata_json(unit.metadata_json)
        assert metadata["source_type"] == "pdf"
        assert metadata["page_number"] == 1
        assert metadata["source_locator"] == "page:1"
        assert metadata["extractor"]
        assert unit.start_char is not None
        assert unit.end_char is not None
        preview_target = _citation_preview_target(unit)
        assert preview_target is not None
        assert preview_target.locator_kind == "pdf_page"
        assert preview_target.page_number == 1


def test_fixed_pdf_round_trip_keeps_page_locator_behavior(
    session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_chunk_strategy(monkeypatch, "fixed")
    storage_path = "fixed-manual.pdf"
    (tmp_path / storage_path).write_bytes(
        _build_minimal_pdf(text="Fixed PDF citation behavior keeps page one locator.")
    )

    with session_factory() as db:
        document = _create_document(
            db,
            original_filename=storage_path,
            storage_path=storage_path,
            file_type="application/pdf",
        )
        process_document(db, document=document, upload_root=tmp_path)
        db.commit()
        document_id = document.id

    with session_factory() as db:
        units = list(
            db.scalars(
                select(DocumentCitationUnit)
                .where(DocumentCitationUnit.document_id == document_id)
                .order_by(DocumentCitationUnit.unit_index.asc())
            )
        )

    assert units
    metadata = _metadata_json(units[0].metadata_json)
    assert metadata["source_type"] == "pdf"
    assert metadata["page_number"] == 1
    assert metadata["source_locator"] == "page:1"
    assert _citation_preview_target(units[0]).locator_kind == "pdf_page"


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
