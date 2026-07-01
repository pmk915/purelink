from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.document_block import DocumentBlock
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.document_index import DocumentIndex
from app.models.enums import (
    DocumentBlockType,
    DocumentIndexStatus,
    DocumentIndexType,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.services.document_status import build_document_status


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


@pytest.fixture
async def document_status_client(session_factory: sessionmaker) -> AsyncClient:
    async def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


def test_ready_document_status_reports_rag_ready(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document_fixture(db)
        _add_blocks_chunks_citations(db, document)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        status = build_document_status(db, document=document)

    assert status["rag_ready"] is True
    assert status["block_count"] == 1
    assert status["chunk_count"] == 1
    assert status["citation_unit_count"] == 1
    assert status["vector_index_status"] == "ready"
    assert status["vector_index_count"] == 1
    assert status["graph_index_status"] == "missing"


def test_missing_chunks_makes_rag_not_ready(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document_fixture(db)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        status = build_document_status(db, document=document)

    assert status["rag_ready"] is False
    assert _check_status(status, "chunks") == "missing"


def test_missing_citation_units_makes_rag_not_ready(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document_fixture(db)
        _add_block_and_chunk_only(db, document)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        status = build_document_status(db, document=document)

    assert status["rag_ready"] is False
    assert _check_status(status, "citation_units") == "missing"


def test_missing_vector_index_makes_rag_not_ready(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document_fixture(db)
        _add_blocks_chunks_citations(db, document)
        status = build_document_status(db, document=document)

    assert status["rag_ready"] is False
    assert status["vector_index_status"] == "missing"


def test_missing_graph_index_is_optional_for_base_rag(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document_fixture(db)
        _add_blocks_chunks_citations(db, document)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        status = build_document_status(db, document=document)

    assert status["rag_ready"] is True
    assert status["graph_index_status"] == "missing"
    assert _check_status(status, "graph_index") == "optional"


def test_failed_processing_status_reports_error_and_not_ready(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        document = _create_document_fixture(
            db,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message="Chunk persistence failed.",
        )
        _add_blocks_chunks_citations(db, document)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        _add_processing_job(
            db,
            document,
            status=ProcessingJobStatus.FAILED,
            step="chunk_persist",
            error_code="CHUNK_PERSIST_FAILED",
            error_message="Chunk persistence failed.",
        )
        status = build_document_status(db, document=document)

    assert status["rag_ready"] is False
    assert status["error_code"] == "CHUNK_PERSIST_FAILED"
    assert status["error_message"] == "Chunk persistence failed."
    assert _check_status(status, "processing") == "failed"


@pytest.mark.anyio
async def test_personal_kb_owner_can_read_document_status(
    document_status_client: AsyncClient,
    session_factory: sessionmaker,
) -> None:
    owner = await _register_and_login(
        document_status_client,
        email="status-owner@example.com",
        username="status-owner",
    )
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    create_response = await document_status_client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": "Status KB"},
    )
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]

    with session_factory() as db:
        document = _create_document_fixture(db, kb_id=kb_id, user_id=int(owner["user_id"]))
        _add_blocks_chunks_citations(db, document)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        db.commit()
        document_id = document.id

    response = await document_status_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/status",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["rag_ready"] is True


@pytest.mark.anyio
async def test_unauthorized_personal_user_cannot_read_document_status(
    document_status_client: AsyncClient,
    session_factory: sessionmaker,
) -> None:
    owner = await _register_and_login(
        document_status_client,
        email="status-owner-private@example.com",
        username="status-owner-private",
    )
    outsider = await _register_and_login(
        document_status_client,
        email="status-outsider@example.com",
        username="status-outsider",
    )
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}
    create_response = await document_status_client.post(
        "/api/v1/knowledge-bases",
        headers=owner_headers,
        json={"name": "Private Status KB"},
    )
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]
    with session_factory() as db:
        document = _create_document_fixture(db, kb_id=kb_id, user_id=int(owner["user_id"]))
        db.commit()
        document_id = document.id

    response = await document_status_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/status",
        headers=outsider_headers,
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_team_member_can_read_document_status(
    document_status_client: AsyncClient,
    session_factory: sessionmaker,
) -> None:
    admin = await _register_and_login(
        document_status_client,
        email="status-team-admin@example.com",
        username="status-team-admin",
    )
    member = await _register_and_login(
        document_status_client,
        email="status-team-member@example.com",
        username="status-team-member",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    team_id = await _create_team(
        document_status_client,
        access_token=str(admin["access_token"]),
        name="Status Team",
    )
    invite_code = await _create_team_invite(
        document_status_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_status_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    create_response = await document_status_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=admin_headers,
        json={"name": "Team Status KB"},
    )
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]
    with session_factory() as db:
        document = _create_document_fixture(
            db,
            kb_id=kb_id,
            user_id=int(admin["user_id"]),
            review_status=DocumentReviewStatus.APPROVED,
        )
        _add_blocks_chunks_citations(db, document)
        _add_index(db, document, DocumentIndexType.VECTOR, DocumentIndexStatus.INDEXED)
        db.commit()
        document_id = document.id

    response = await document_status_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents/{document_id}/status",
        headers=member_headers,
    )

    assert response.status_code == 200
    assert response.json()["document_id"] == document_id


@pytest.mark.anyio
async def test_document_status_not_found_returns_404(
    document_status_client: AsyncClient,
) -> None:
    user = await _register_and_login(
        document_status_client,
        email="status-not-found@example.com",
        username="status-not-found",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    create_response = await document_status_client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": "Status 404 KB"},
    )
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]

    response = await document_status_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/documents/999/status",
        headers=headers,
    )

    assert response.status_code == 404


def _create_document_fixture(
    db: Session,
    *,
    kb_id: int | None = None,
    user_id: int | None = None,
    review_status: DocumentReviewStatus = DocumentReviewStatus.NOT_REQUIRED,
    processing_status: DocumentProcessingStatus = DocumentProcessingStatus.INDEXED,
    error_message: str | None = None,
) -> Document:
    if user_id is None:
        user = User(email="status-fixture@example.com", username="status-fixture", hashed_password="hashed")
        db.add(user)
        db.flush()
        user_id = user.id
    if kb_id is None:
        kb = KnowledgeBase(name="Status Fixture KB", scope=KnowledgeBaseScope.PERSONAL, owner_id=user_id)
        db.add(kb)
        db.flush()
        kb_id = kb.id
    document = Document(
        knowledge_base_id=kb_id,
        owner_id=user_id,
        submitted_by=user_id,
        filename="status.md",
        original_filename="status.md",
        file_type="text/markdown",
        file_size=128,
        storage_path=f"status/{kb_id}/status.md",
        review_status=review_status,
        processing_status=processing_status,
        error_message=error_message,
    )
    db.add(document)
    db.flush()
    return document


def _add_block_and_chunk_only(db: Session, document: Document) -> DocumentChunk:
    db.add(
        DocumentBlock(
            document_id=document.id,
            block_type=DocumentBlockType.TEXT,
            text="管理员可以删除文档。",
            order_index=0,
        )
    )
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_key=f"document:{document.id}:chunk:0",
        chunk_index=0,
        chunk_text="管理员可以删除文档。",
    )
    db.add(chunk)
    db.flush()
    return chunk


def _add_blocks_chunks_citations(db: Session, document: Document) -> None:
    chunk = _add_block_and_chunk_only(db, document)
    db.add(
        DocumentCitationUnit(
            document_id=document.id,
            chunk_id=chunk.id,
            knowledge_base_id=document.knowledge_base_id,
            chunk_key=chunk.chunk_key,
            unit_index=0,
            unit_text=chunk.chunk_text,
        )
    )
    db.flush()


def _add_index(
    db: Session,
    document: Document,
    index_type: DocumentIndexType,
    status: DocumentIndexStatus,
) -> DocumentIndex:
    index = DocumentIndex(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        index_type=index_type,
        provider="local_hashed_bow" if index_type == DocumentIndexType.VECTOR else "local_rule",
        model_name="hashed_bow_v1" if index_type == DocumentIndexType.VECTOR else "local_rule_graph_extractor",
        model_dim=128 if index_type == DocumentIndexType.VECTOR else None,
        status=status,
        indexed_at=datetime.now(UTC) if status == DocumentIndexStatus.INDEXED else None,
    )
    db.add(index)
    db.flush()
    return index


def _add_processing_job(
    db: Session,
    document: Document,
    *,
    status: ProcessingJobStatus,
    step: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> ProcessingJob:
    job = ProcessingJob(
        document_id=document.id,
        triggered_by_id=document.owner_id,
        job_type=ProcessingJobType.DOCUMENT_PROCESS,
        trigger_type=ProcessingJobTrigger.PROCESS,
        status=status,
        current_step=step,
        error_code=error_code,
        error_message=error_message,
    )
    db.add(job)
    db.flush()
    return job


def _check_status(status: dict[str, object], name: str) -> str | None:
    for check in status["checks"]:
        if check["name"] == name:
            return str(check["status"])
    return None


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str,
    username: str,
    password: str = "StrongPass123",
) -> dict[str, str | int]:
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200

    return {
        "access_token": login_response.json()["access_token"],
        "user_id": register_response.json()["id"],
    }


async def _create_team(client: AsyncClient, *, access_token: str, name: str) -> int:
    response = await client.post(
        "/api/v1/teams",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_team_invite(
    client: AsyncClient,
    *,
    access_token: str,
    team_id: int,
) -> str:
    response = await client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"expires_in_days": 7},
    )
    assert response.status_code == 201
    return response.json()["code"]


async def _join_team(
    client: AsyncClient,
    *,
    access_token: str,
    code: str,
) -> None:
    response = await client.post(
        "/api/v1/team-invites/join",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": code},
    )
    assert response.status_code == 200
