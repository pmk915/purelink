from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.enums import DocumentProcessingStatus, ProcessingJobStatus
from app.models.processing_job import ProcessingJob
from app.services import processing_worker as processing_worker_service


load_all_models()


@pytest.fixture
def test_session_factory() -> sessionmaker:
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
async def processing_job_client(
    test_session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncClient:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PARSED_DIR", str(tmp_path / "parsed"))
    monkeypatch.setenv("CHUNK_DIR", str(tmp_path / "chunks"))
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path / "vector_store"))
    get_settings.cache_clear()

    monkeypatch.setattr(
        processing_worker_service,
        "submit_processing_job",
        lambda *, job: str(job.id),
    )
    monkeypatch.setattr(
        processing_worker_service,
        "open_processing_session",
        lambda: test_session_factory(),
    )

    async def override_get_db():
        db = test_session_factory()
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
    get_settings.cache_clear()


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str,
    username: str,
) -> dict[str, str | int]:
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "StrongPass123",
        },
    )
    assert register_response.status_code == 201
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": email,
            "password": "StrongPass123",
        },
    )
    assert login_response.status_code == 200
    return {
        "access_token": login_response.json()["access_token"],
        "user_id": register_response.json()["id"],
    }


async def _create_personal_knowledge_base(
    client: AsyncClient,
    *,
    access_token: str,
    name: str,
) -> int:
    response = await client.post(
        "/api/v1/knowledge-bases",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


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


async def _join_team(client: AsyncClient, *, access_token: str, code: str) -> None:
    response = await client.post(
        "/api/v1/team-invites/join",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"code": code},
    )
    assert response.status_code == 200


async def _create_team_knowledge_base(
    client: AsyncClient,
    *,
    access_token: str,
    team_id: int,
    name: str,
) -> int:
    response = await client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _upload_personal_document(
    client: AsyncClient,
    *,
    access_token: str,
    kb_id: int,
    filename: str = "job.txt",
) -> int:
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"file": (filename, b"processing job dashboard source", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _upload_team_document(
    client: AsyncClient,
    *,
    access_token: str,
    team_id: int,
    kb_id: int,
    filename: str = "team-job.txt",
) -> int:
    response = await client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents",
        headers={"Authorization": f"Bearer {access_token}"},
        files={"file": (filename, b"team processing job source", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _mark_latest_job_failed(
    session_factory: sessionmaker,
    *,
    document_id: int,
    error_code: str = "DOCUMENT_PROCESSING_FAILED",
) -> int:
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )
        assert job is not None
        document.processing_status = DocumentProcessingStatus.FAILED
        document.error_message = "Simulated processing failure."
        job.status = ProcessingJobStatus.FAILED
        job.current_step = "extract_text"
        job.error_code = error_code
        job.error_message = "Simulated processing failure."
        job.finished_at = datetime.now(UTC)
        db.commit()
        return job.id


@pytest.mark.anyio
async def test_personal_owner_can_list_processing_jobs_with_retry_state(
    processing_job_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    user = await _register_and_login(
        processing_job_client,
        email="jobs-owner@example.com",
        username="jobs-owner",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    kb_id = await _create_personal_knowledge_base(
        processing_job_client,
        access_token=str(user["access_token"]),
        name="Jobs KB",
    )
    document_id = await _upload_personal_document(
        processing_job_client,
        access_token=str(user["access_token"]),
        kb_id=kb_id,
    )
    _mark_latest_job_failed(test_session_factory, document_id=document_id)

    response = await processing_job_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/processing-jobs",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["failed_count"] == 1
    assert body["items"][0]["document_id"] == document_id
    assert body["items"][0]["can_retry"] is True


@pytest.mark.anyio
async def test_running_processing_job_has_can_retry_false(
    processing_job_client: AsyncClient,
) -> None:
    user = await _register_and_login(
        processing_job_client,
        email="jobs-running@example.com",
        username="jobs-running",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    kb_id = await _create_personal_knowledge_base(
        processing_job_client,
        access_token=str(user["access_token"]),
        name="Running Jobs KB",
    )
    document_id = await _upload_personal_document(
        processing_job_client,
        access_token=str(user["access_token"]),
        kb_id=kb_id,
    )

    response = await processing_job_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/processing-jobs",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["running_count"] == 1
    assert body["items"][0]["document_id"] == document_id
    assert body["items"][0]["can_retry"] is False


@pytest.mark.anyio
async def test_personal_retry_creates_new_queued_job(
    processing_job_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    user = await _register_and_login(
        processing_job_client,
        email="jobs-retry@example.com",
        username="jobs-retry",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    kb_id = await _create_personal_knowledge_base(
        processing_job_client,
        access_token=str(user["access_token"]),
        name="Retry KB",
    )
    document_id = await _upload_personal_document(
        processing_job_client,
        access_token=str(user["access_token"]),
        kb_id=kb_id,
    )
    failed_job_id = _mark_latest_job_failed(test_session_factory, document_id=document_id)

    response = await processing_job_client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/retry-processing",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["trigger_type"] == "retry"
    assert body["job_status"] == "queued"
    assert body["attempt_number"] == 2

    with test_session_factory() as db:
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.id.asc())
            )
        )
    assert [job.id for job in jobs] == [failed_job_id, body["job_id"]]
    assert jobs[-1].status == ProcessingJobStatus.QUEUED


@pytest.mark.anyio
async def test_retry_missing_source_returns_clear_error(
    processing_job_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    user = await _register_and_login(
        processing_job_client,
        email="jobs-missing-source@example.com",
        username="jobs-missing-source",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    kb_id = await _create_personal_knowledge_base(
        processing_job_client,
        access_token=str(user["access_token"]),
        name="Missing Source Retry KB",
    )
    document_id = await _upload_personal_document(
        processing_job_client,
        access_token=str(user["access_token"]),
        kb_id=kb_id,
    )
    _mark_latest_job_failed(test_session_factory, document_id=document_id)
    with test_session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        source_path = Path(get_settings().upload_dir) / document.storage_path
    source_path.unlink()

    response = await processing_job_client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/retry-processing",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROCESSING_SOURCE_MISSING"


@pytest.mark.anyio
async def test_retry_blocked_when_active_job_exists(
    processing_job_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    user = await _register_and_login(
        processing_job_client,
        email="jobs-active@example.com",
        username="jobs-active",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    kb_id = await _create_personal_knowledge_base(
        processing_job_client,
        access_token=str(user["access_token"]),
        name="Active Retry KB",
    )
    document_id = await _upload_personal_document(
        processing_job_client,
        access_token=str(user["access_token"]),
        kb_id=kb_id,
    )
    _mark_latest_job_failed(test_session_factory, document_id=document_id)
    with test_session_factory() as db:
        failed_job = db.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id.desc())
        )
        assert failed_job is not None
        active_job = ProcessingJob(
            document_id=document_id,
            triggered_by_id=int(user["user_id"]),
            previous_job_id=failed_job.id,
            job_type=failed_job.job_type,
            trigger_type=failed_job.trigger_type,
            status=ProcessingJobStatus.QUEUED,
            current_step="queued",
            attempt_number=2,
        )
        db.add(active_job)
        db.commit()

    response = await processing_job_client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/retry-processing",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROCESSING_JOB_ALREADY_RUNNING"


@pytest.mark.anyio
async def test_team_member_can_list_but_cannot_retry_and_admin_can_retry(
    processing_job_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    admin = await _register_and_login(
        processing_job_client,
        email="jobs-admin@example.com",
        username="jobs-admin",
    )
    member = await _register_and_login(
        processing_job_client,
        email="jobs-member@example.com",
        username="jobs-member",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    team_id = await _create_team(
        processing_job_client,
        access_token=str(admin["access_token"]),
        name="Jobs Team",
    )
    invite_code = await _create_team_invite(
        processing_job_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        processing_job_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    kb_id = await _create_team_knowledge_base(
        processing_job_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Team Jobs KB",
    )
    document_id = await _upload_team_document(
        processing_job_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        kb_id=kb_id,
    )
    _mark_latest_job_failed(test_session_factory, document_id=document_id)

    list_response = await processing_job_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/processing-jobs",
        headers=member_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["can_retry"] is True

    member_retry = await processing_job_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents/{document_id}/retry-processing",
        headers=member_headers,
    )
    assert member_retry.status_code == 403
    assert member_retry.json()["error"]["code"] == "FORBIDDEN"

    admin_retry = await processing_job_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents/{document_id}/retry-processing",
        headers=admin_headers,
    )
    assert admin_retry.status_code == 200
    assert admin_retry.json()["trigger_type"] == "retry"


@pytest.mark.anyio
async def test_unauthorized_user_cannot_list_processing_jobs(
    processing_job_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    owner = await _register_and_login(
        processing_job_client,
        email="jobs-private-owner@example.com",
        username="jobs-private-owner",
    )
    other = await _register_and_login(
        processing_job_client,
        email="jobs-private-other@example.com",
        username="jobs-private-other",
    )
    kb_id = await _create_personal_knowledge_base(
        processing_job_client,
        access_token=str(owner["access_token"]),
        name="Private Jobs KB",
    )
    document_id = await _upload_personal_document(
        processing_job_client,
        access_token=str(owner["access_token"]),
        kb_id=kb_id,
    )
    _mark_latest_job_failed(test_session_factory, document_id=document_id)

    response = await processing_job_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/processing-jobs",
        headers={"Authorization": f"Bearer {other['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
