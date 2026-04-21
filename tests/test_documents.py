from __future__ import annotations

import json
from pathlib import Path

import pytest
import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document_task import DocumentTask
from app.models.enums import DocumentTaskStatus


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
async def document_client(
    test_session_factory: sessionmaker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncClient:
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("PARSED_DIR", str(tmp_path / "parsed"))
    monkeypatch.setenv("CHUNK_DIR", str(tmp_path / "chunks"))
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path / "vector_store"))
    get_settings.cache_clear()

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


@pytest.mark.anyio
async def test_personal_document_upload_and_list_respect_owner_boundary(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="personal-docs-owner@example.com",
        username="personal-docs-owner",
    )
    bob = await _register_and_login(
        document_client,
        email="personal-docs-other@example.com",
        username="personal-docs-other",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Alice Private Docs",
    )

    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("alice-notes.txt", b"Alice private document", "text/plain")},
    )

    assert upload_response.status_code == 201
    document_body = upload_response.json()
    assert document_body["knowledge_base_id"] == knowledge_base_id
    assert document_body["owner_id"] == alice["user_id"]
    assert document_body["submitted_by"] == alice["user_id"]
    assert document_body["original_filename"] == "alice-notes.txt"
    assert document_body["file_type"] == "text/plain"
    assert document_body["review_status"] == "not_required"
    assert document_body["processing_status"] == "uploaded"
    assert document_body["reviewed_by"] is None
    assert document_body["reviewed_at"] is None
    assert "personal/knowledge_base_" in document_body["storage_path"]

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"Alice private document"

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["id"] == document_body["id"]

    other_list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=bob_headers,
    )
    other_upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=bob_headers,
        files={"file": ("intrusion.txt", b"nope", "text/plain")},
    )
    assert other_list_response.status_code == 404
    assert other_upload_response.status_code == 404


@pytest.mark.anyio
async def test_team_document_submission_is_pending_review_and_not_visible_as_approved(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="team-docs-admin@example.com",
        username="team-docs-admin",
    )
    member = await _register_and_login(
        document_client,
        email="team-docs-member@example.com",
        username="team-docs-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="team-docs-outsider@example.com",
        username="team-docs-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Review Flow Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Shared Review Docs",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("team-proposal.pdf", b"team review content", "application/pdf")},
    )

    assert upload_response.status_code == 201
    document_body = upload_response.json()
    assert document_body["knowledge_base_id"] == knowledge_base_id
    assert document_body["owner_id"] == member["user_id"]
    assert document_body["submitted_by"] == member["user_id"]
    assert document_body["review_status"] == "pending_review"
    assert document_body["processing_status"] == "uploaded"
    assert document_body["reviewed_by"] is None
    assert document_body["reviewed_at"] is None
    assert document_body["review_comment"] is None
    assert document_body["review_status"] != "approved"
    assert f"team/team_{team_id}/knowledge_base_{knowledge_base_id}/" in document_body["storage_path"]

    saved_file = tmp_path / "uploads" / document_body["storage_path"]
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"team review content"

    member_list_response = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
    )
    admin_list_response = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=admin_headers,
    )
    outsider_list_response = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=outsider_headers,
    )
    outsider_upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=outsider_headers,
        files={"file": ("outsider.txt", b"forbidden", "text/plain")},
    )

    assert member_list_response.status_code == 200
    assert admin_list_response.status_code == 200
    assert outsider_list_response.status_code == 404
    assert outsider_upload_response.status_code == 404

    member_documents = member_list_response.json()
    admin_documents = admin_list_response.json()
    assert len(member_documents) == 1
    assert len(admin_documents) == 1
    assert member_documents[0]["id"] == document_body["id"]
    assert admin_documents[0]["review_status"] == "pending_review"
    assert admin_documents[0]["processing_status"] == "uploaded"


@pytest.mark.anyio
async def test_team_document_review_permissions_and_state_transitions(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="review-admin@example.com",
        username="review-admin",
    )
    member = await _register_and_login(
        document_client,
        email="review-member@example.com",
        username="review-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="review-outsider@example.com",
        username="review-outsider",
    )
    other_admin = await _register_and_login(
        document_client,
        email="other-review-admin@example.com",
        username="other-review-admin",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}
    other_admin_headers = {"Authorization": f"Bearer {other_admin['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Review Admin Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Review Queue Docs",
    )
    other_team_id = await _create_team(
        document_client,
        access_token=str(other_admin["access_token"]),
        name="Other Review Team",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("pending-review.txt", b"pending review", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    member_review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=member_headers,
    )
    outsider_review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=outsider_headers,
    )
    member_approve = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=member_headers,
    )
    outsider_approve = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=outsider_headers,
    )
    wrong_team_approve = await document_client.post(
        f"/api/v1/teams/{other_team_id}/documents/{document_id}/approve",
        headers=other_admin_headers,
    )

    assert member_review_tasks.status_code == 403
    assert outsider_review_tasks.status_code == 404
    assert member_approve.status_code == 403
    assert outsider_approve.status_code == 404
    assert wrong_team_approve.status_code == 404

    review_tasks = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks.status_code == 200
    tasks_body = review_tasks.json()
    assert len(tasks_body) == 1
    assert tasks_body[0]["id"] == document_id
    assert tasks_body[0]["review_status"] == "pending_review"
    assert tasks_body[0]["processing_status"] == "uploaded"

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    approved_body = approve_response.json()
    assert approved_body["review_status"] == "approved"
    assert approved_body["processing_status"] == "uploaded"
    assert approved_body["reviewed_by"] == admin["user_id"]
    assert approved_body["reviewed_at"] is not None
    assert approved_body["review_comment"] is None

    review_tasks_after_approve = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks_after_approve.status_code == 200
    assert review_tasks_after_approve.json() == []

    repeated_approve = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    repeated_reject = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/reject",
        headers=admin_headers,
        json={"review_comment": "Too late"},
    )
    assert repeated_approve.status_code == 409
    assert repeated_reject.status_code == 409


@pytest.mark.anyio
async def test_team_document_reject_records_reason_and_blocks_repeat_review(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="reject-admin@example.com",
        username="reject-admin",
    )
    member = await _register_and_login(
        document_client,
        email="reject-member@example.com",
        username="reject-member",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Reject Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Reject Queue Docs",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("reject-me.txt", b"reject me", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    reject_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/reject",
        headers=admin_headers,
        json={"review_comment": "File content does not meet team policy."},
    )
    assert reject_response.status_code == 200
    rejected_body = reject_response.json()
    assert rejected_body["review_status"] == "rejected"
    assert rejected_body["processing_status"] == "uploaded"
    assert rejected_body["reviewed_by"] == admin["user_id"]
    assert rejected_body["reviewed_at"] is not None
    assert rejected_body["review_comment"] == "File content does not meet team policy."

    review_tasks_after_reject = await document_client.get(
        f"/api/v1/teams/{team_id}/review-tasks",
        headers=admin_headers,
    )
    assert review_tasks_after_reject.status_code == 200
    assert review_tasks_after_reject.json() == []

    repeated_reject = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/reject",
        headers=admin_headers,
        json={"review_comment": "Still rejected"},
    )
    assert repeated_reject.status_code == 409


@pytest.mark.anyio
async def test_personal_txt_document_can_be_parsed_and_saved_to_local_result(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="parse-personal@example.com",
        username="parse-personal",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Parse Personal KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("notes.txt", b"line one\nline two", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200
    parse_body = parse_response.json()
    assert parse_body["document_id"] == document_id
    assert parse_body["knowledge_base_id"] == knowledge_base_id
    assert parse_body["processing_status"] == "parsed"
    assert parse_body["parser"] == "plain_text"
    assert parse_body["extracted_char_count"] == len("line one\nline two")

    parsed_file = tmp_path / "parsed" / parse_body["parsed_path"]
    assert parsed_file.exists()
    parsed_payload = json.loads(parsed_file.read_text(encoding="utf-8"))
    assert parsed_payload["document_id"] == document_id
    assert parsed_payload["content"] == "line one\nline two"
    assert parsed_payload["parser"] == "plain_text"

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "parsed"


@pytest.mark.anyio
async def test_team_document_must_be_approved_before_it_can_be_parsed(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="parse-team-admin@example.com",
        username="parse-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="parse-team-member@example.com",
        username="parse-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="parse-team-outsider@example.com",
        username="parse-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Parse Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Parse Team KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("team-notes.md", b"# Heading\n\nApproved content", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    outsider_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=outsider_headers,
    )
    assert parse_before_approval.status_code == 409
    assert outsider_parse.status_code == 404

    list_before_approval = await document_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=admin_headers,
    )
    assert list_before_approval.status_code == 200
    assert list_before_approval.json()[0]["processing_status"] == "uploaded"

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["review_status"] == "approved"

    parse_after_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    assert parse_after_approval.status_code == 200
    parse_body = parse_after_approval.json()
    assert parse_body["processing_status"] == "parsed"
    assert parse_body["parser"] == "markdown"

    parsed_file = tmp_path / "parsed" / parse_body["parsed_path"]
    assert parsed_file.exists()
    parsed_payload = json.loads(parsed_file.read_text(encoding="utf-8"))
    assert parsed_payload["scope"] == "team"
    assert parsed_payload["team_id"] == team_id
    assert parsed_payload["content"] == "# Heading\n\nApproved content"


@pytest.mark.anyio
async def test_unsupported_document_parse_marks_processing_failed(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="parse-fail@example.com",
        username="parse-fail",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Parse Fail KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("unsupported.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 400

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "failed"


@pytest.mark.anyio
async def test_invalid_chunk_input_marks_processing_failed(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="chunk-fail@example.com",
        username="chunk-fail",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Chunk Fail KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("chunk-fail.txt", b"valid content", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    parsed_file = tmp_path / "parsed" / parse_response.json()["parsed_path"]
    parsed_file.write_text(
        json.dumps({"content": ""}),
        encoding="utf-8",
    )

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 400

    list_response = await document_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["processing_status"] == "failed"


@pytest.mark.anyio
async def test_personal_document_parse_task_creation_and_status_query(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="task-personal-owner@example.com",
        username="task-personal-owner",
    )
    bob = await _register_and_login(
        document_client,
        email="task-personal-other@example.com",
        username="task-personal-other",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Task KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("task-notes.txt", b"task me", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    create_task_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert create_task_response.status_code == 201
    task_body = create_task_response.json()
    task_id = task_body["id"]
    assert task_body["document_id"] == document_id
    assert task_body["task_type"] == "parse"
    assert task_body["status"] == "pending"
    assert task_body["error_message"] is None
    assert task_body["retry_count"] == 0
    assert task_body["started_at"] is None
    assert task_body["finished_at"] is None

    get_owner_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=alice_headers,
    )
    get_other_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=bob_headers,
    )
    assert get_owner_task.status_code == 200
    assert get_owner_task.json()["id"] == task_id
    assert get_other_task.status_code == 404


@pytest.mark.anyio
async def test_personal_document_parse_task_rejects_duplicate_active_tasks(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="task-dedupe-owner@example.com",
        username="task-dedupe-owner",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Dedupe KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("task-dedupe.txt", b"dedupe me", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    first_task_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert first_task_response.status_code == 201
    first_task_id = first_task_response.json()["id"]

    duplicate_pending_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert duplicate_pending_response.status_code == 409

    with test_session_factory() as db:
        task = db.get(DocumentTask, first_task_id)
        assert task is not None
        task.status = DocumentTaskStatus.SUCCEEDED
        db.commit()

    create_after_completion = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=alice_headers,
    )
    assert create_after_completion.status_code == 201


@pytest.mark.anyio
async def test_personal_document_chunk_embed_and_index_task_creation_requires_prerequisites(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="task-chain-personal@example.com",
        username="task-chain-personal",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Task Chain KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("task-chain.txt", b"task chain content", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    chunk_before_parse = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=alice_headers,
    )
    embed_before_parse = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=alice_headers,
    )
    index_before_parse = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=alice_headers,
    )
    assert chunk_before_parse.status_code == 409
    assert embed_before_parse.status_code == 409
    assert index_before_parse.status_code == 409

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    chunk_task = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=alice_headers,
    )
    embed_before_chunk = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=alice_headers,
    )
    index_before_chunk = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=alice_headers,
    )
    assert chunk_task.status_code == 201
    assert chunk_task.json()["task_type"] == "chunk"
    assert chunk_task.json()["status"] == "pending"
    assert embed_before_chunk.status_code == 409
    assert index_before_chunk.status_code == 409

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 200

    embed_task = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=alice_headers,
    )
    index_task = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=alice_headers,
    )
    assert embed_task.status_code == 201
    assert embed_task.json()["task_type"] == "embed"
    assert index_task.status_code == 201
    assert index_task.json()["task_type"] == "index"


@pytest.mark.anyio
async def test_team_document_parse_task_creation_requires_approved_document_and_member_access(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="task-team-admin@example.com",
        username="task-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="task-team-member@example.com",
        username="task-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="task-team-outsider@example.com",
        username="task-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Task Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Task Team KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("task-team.md", b"# Task Team", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    create_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    outsider_create = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=outsider_headers,
    )
    assert create_before_approval.status_code == 409
    assert outsider_create.status_code == 404

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    create_after_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    assert create_after_approval.status_code == 201
    task_body = create_after_approval.json()
    task_id = task_body["id"]
    assert task_body["document_id"] == document_id
    assert task_body["task_type"] == "parse"
    assert task_body["status"] == "pending"

    admin_get_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=admin_headers,
    )
    member_get_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=member_headers,
    )
    outsider_get_task = await document_client.get(
        f"/api/v1/document-tasks/{task_id}",
        headers=outsider_headers,
    )
    assert admin_get_task.status_code == 200
    assert member_get_task.status_code == 200
    assert outsider_get_task.status_code == 404


@pytest.mark.anyio
async def test_team_document_parse_task_rejects_duplicate_processing_task(
    document_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="task-processing-admin@example.com",
        username="task-processing-admin",
    )
    member = await _register_and_login(
        document_client,
        email="task-processing-member@example.com",
        username="task-processing-member",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Task Processing Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Task Processing KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("task-processing.md", b"# approved", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    first_task_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    assert first_task_response.status_code == 201
    first_task_id = first_task_response.json()["id"]

    with test_session_factory() as db:
        task = db.get(DocumentTask, first_task_id)
        assert task is not None
        task.status = DocumentTaskStatus.PROCESSING
        db.commit()

    duplicate_processing_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks",
        headers=member_headers,
    )
    assert duplicate_processing_response.status_code == 409


@pytest.mark.anyio
async def test_team_document_chunk_embed_and_index_tasks_require_member_access_and_approval(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="task-chain-team-admin@example.com",
        username="task-chain-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="task-chain-team-member@example.com",
        username="task-chain-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="task-chain-team-outsider@example.com",
        username="task-chain-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Task Chain Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Task Chain Team KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("task-chain-team.md", b"team task chain", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    outsider_chunk_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=outsider_headers,
    )
    member_chunk_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=member_headers,
    )
    assert outsider_chunk_task.status_code == 404
    assert member_chunk_before_approval.status_code == 409

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    chunk_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=member_headers,
    )
    embed_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=member_headers,
    )
    index_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=member_headers,
    )
    assert chunk_before_parse.status_code == 409
    assert embed_before_parse.status_code == 409
    assert index_before_parse.status_code == 409

    parse_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    assert parse_response.status_code == 200

    chunk_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
        headers=member_headers,
    )
    assert chunk_task.status_code == 201
    assert chunk_task.json()["task_type"] == "chunk"

    chunk_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_response.status_code == 200

    embed_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks",
        headers=member_headers,
    )
    index_task = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks",
        headers=member_headers,
    )
    assert embed_task.status_code == 201
    assert embed_task.json()["task_type"] == "embed"
    assert index_task.status_code == 201
    assert index_task.json()["task_type"] == "index"


@pytest.mark.anyio
async def test_personal_parsed_document_can_be_chunked_to_local_result(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="chunk-personal@example.com",
        username="chunk-personal",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Chunk Personal KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("chunk-notes.txt", b"alpha\n\nbeta\n\ngamma", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 200
    chunk_body = chunk_response.json()
    assert chunk_body["document_id"] == document_id
    assert chunk_body["processing_status"] == "parsed"
    assert chunk_body["chunk_count"] >= 1
    assert chunk_body["source_parsed_path"].endswith(f"document_{document_id}.json")

    chunk_file = tmp_path / "chunks" / chunk_body["chunked_path"]
    assert chunk_file.exists()
    chunk_payload = json.loads(chunk_file.read_text(encoding="utf-8"))
    assert chunk_payload["document_id"] == document_id
    assert chunk_payload["chunk_count"] == chunk_body["chunk_count"]
    assert chunk_payload["chunks"][0]["chunk_id"] == f"{document_id}:0"
    assert "alpha" in chunk_payload["chunks"][0]["text"]


@pytest.mark.anyio
async def test_team_document_must_be_approved_and_parsed_before_chunking(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="chunk-team-admin@example.com",
        username="chunk-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="chunk-team-member@example.com",
        username="chunk-team-member",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Chunk Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Chunk Team KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("chunk-team.md", b"# Heading\n\nApproved chunk content", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    chunk_before_approval = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_before_approval.status_code == 409

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    chunk_before_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_before_parse.status_code == 409

    parse_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=member_headers,
    )
    assert parse_response.status_code == 200

    chunk_after_parse = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_after_parse.status_code == 200
    chunk_body = chunk_after_parse.json()
    assert chunk_body["processing_status"] == "parsed"
    assert chunk_body["chunk_count"] >= 1

    chunk_file = tmp_path / "chunks" / chunk_body["chunked_path"]
    assert chunk_file.exists()
    chunk_payload = json.loads(chunk_file.read_text(encoding="utf-8"))
    assert chunk_payload["team_id"] == team_id
    assert chunk_payload["source_parsed_path"].endswith(f"document_{document_id}.json")


@pytest.mark.anyio
async def test_personal_document_can_be_embedded_and_retrieved(
    document_client: AsyncClient,
    tmp_path: Path,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="embed-personal@example.com",
        username="embed-personal",
    )
    bob = await _register_and_login(
        document_client,
        email="embed-personal-other@example.com",
        username="embed-personal-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal Retrieval KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("embed-notes.txt", b"alpha retrieval target\n\nbeta gamma", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    parse_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
        headers=alice_headers,
    )
    assert parse_response.status_code == 200

    chunk_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
        headers=alice_headers,
    )
    assert chunk_response.status_code == 200

    embed_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
        headers=alice_headers,
    )
    assert embed_response.status_code == 200
    embed_body = embed_response.json()
    assert embed_body["document_id"] == document_id
    assert embed_body["processing_status"] == "indexed"
    assert embed_body["embedded_chunk_count"] >= 1

    index_file = tmp_path / "vector_store" / embed_body["index_path"]
    assert index_file.exists()
    index_payload = json.loads(index_file.read_text(encoding="utf-8"))
    assert index_payload["knowledge_base_id"] == knowledge_base_id

    retrieve_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=alice_headers,
        json={"query": "retrieval target", "top_k": 3},
    )
    assert retrieve_response.status_code == 200
    retrieve_body = retrieve_response.json()
    assert retrieve_body["query"] == "retrieval target"
    assert retrieve_body["top_k"] == 3
    assert retrieve_body["results"]
    first_result = retrieve_body["results"][0]
    assert first_result["document_id"] == document_id
    assert first_result["knowledge_base_id"] == knowledge_base_id
    assert first_result["scope"] == "personal"
    assert first_result["team_id"] is None
    assert "retrieval target" in first_result["text"]

    other_user_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=bob_headers,
        json={"query": "retrieval target"},
    )
    assert other_user_response.status_code == 404


@pytest.mark.anyio
async def test_team_unapproved_document_cannot_be_embedded_or_retrieved(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="embed-team-admin@example.com",
        username="embed-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="embed-team-member@example.com",
        username="embed-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="embed-team-outsider@example.com",
        username="embed-team-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Embedding Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Embedding Team KB",
    )

    pending_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("pending-note.md", b"pendingonlytoken draft review", "text/markdown")},
    )
    assert pending_upload.status_code == 201
    pending_document_id = pending_upload.json()["id"]

    pending_embed = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{pending_document_id}/embed",
        headers=member_headers,
    )
    assert pending_embed.status_code == 409

    approved_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("approved-note.md", b"approvedtoken searchable knowledge", "text/markdown")},
    )
    assert approved_upload.status_code == 201
    approved_document_id = approved_upload.json()["id"]

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{approved_document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    parse_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/parse",
        headers=member_headers,
    )
    assert parse_response.status_code == 200

    chunk_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/chunk",
        headers=member_headers,
    )
    assert chunk_response.status_code == 200

    embed_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/embed",
        headers=member_headers,
    )
    assert embed_response.status_code == 200
    assert embed_response.json()["processing_status"] == "indexed"

    retrieve_pending_token = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=member_headers,
        json={"query": "pendingonlytoken", "top_k": 5},
    )
    assert retrieve_pending_token.status_code == 200
    assert retrieve_pending_token.json()["results"] == []

    retrieve_approved = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=member_headers,
        json={"query": "approvedtoken", "top_k": 5},
    )
    assert retrieve_approved.status_code == 200
    approved_results = retrieve_approved.json()["results"]
    assert approved_results
    assert approved_results[0]["document_id"] == approved_document_id
    assert approved_results[0]["scope"] == "team"
    assert approved_results[0]["team_id"] == team_id

    outsider_retrieve = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve",
        headers=outsider_headers,
        json={"query": "approvedtoken"},
    )
    assert outsider_retrieve.status_code == 404


@pytest.mark.anyio
async def test_personal_knowledge_base_ask_returns_answer_and_citations(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="ask-personal@example.com",
        username="ask-personal",
    )
    bob = await _register_and_login(
        document_client,
        email="ask-personal-other@example.com",
        username="ask-personal-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Personal QA KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("qa-notes.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
            headers=alice_headers,
        )
    ).status_code == 200

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    ask_body = ask_response.json()
    assert "PureLink" in ask_body["answer"]
    assert ask_body["citations"]
    citation = ask_body["citations"][0]
    assert citation["chunk_id"] == f"{document_id}:0"
    assert citation["document_id"] == document_id
    assert citation["knowledge_base_id"] == knowledge_base_id
    assert citation["scope"] == "personal"
    assert citation["team_id"] is None
    assert "internal docs" in citation["text"]

    other_user_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=bob_headers,
        json={"question": "What does PureLink store?"},
    )
    assert other_user_response.status_code == 404


@pytest.mark.anyio
async def test_team_knowledge_base_ask_uses_only_approved_indexed_documents(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="ask-team-admin@example.com",
        username="ask-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="ask-team-member@example.com",
        username="ask-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="ask-team-outsider@example.com",
        username="ask-team-outsider",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="QA Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="QA Team KB",
    )

    pending_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("qa-pending.md", b"pendingansweronly hidden draft", "text/markdown")},
    )
    assert pending_upload.status_code == 201

    approved_upload = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("qa-approved.md", b"approvedanswer Knowledge base answers for the team.", "text/markdown")},
    )
    assert approved_upload.status_code == 201
    approved_document_id = approved_upload.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/documents/{approved_document_id}/approve",
            headers=admin_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/parse",
            headers=member_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/chunk",
            headers=member_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{approved_document_id}/embed",
            headers=member_headers,
        )
    ).status_code == 200

    ask_pending = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=member_headers,
        json={"question": "pendingansweronly", "top_k": 5},
    )
    assert ask_pending.status_code == 200
    assert ask_pending.json()["citations"] == []

    ask_approved = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=member_headers,
        json={"question": "What are the answers for the team?", "top_k": 5},
    )
    assert ask_approved.status_code == 200
    approved_body = ask_approved.json()
    assert "Knowledge base answers" in approved_body["answer"]
    assert approved_body["citations"]
    citation = approved_body["citations"][0]
    assert citation["document_id"] == approved_document_id
    assert citation["knowledge_base_id"] == knowledge_base_id
    assert citation["scope"] == "team"
    assert citation["team_id"] == team_id

    outsider_ask = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=outsider_headers,
        json={"question": "What are the answers for the team?"},
    )
    assert outsider_ask.status_code == 404


@pytest.mark.anyio
async def test_personal_knowledge_base_ask_can_use_openai_compatible_provider(
    document_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="ask-real-llm@example.com",
        username="ask-real-llm",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Real LLM QA KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("real-qa.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk",
            headers=alice_headers,
        )
    ).status_code == 200
    assert (
        await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed",
            headers=alice_headers,
        )
    ).status_code == 200

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_BASE", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    get_settings.cache_clear()

    captured_request: dict[str, object] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> httpx.Response:
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["json"] = json
        captured_request["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "PureLink stores internal docs for teams."
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.llm.httpx.post", fake_post)

    ask_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?", "top_k": 3},
    )
    assert ask_response.status_code == 200
    ask_body = ask_response.json()
    assert ask_body["answer"] == "PureLink stores internal docs for teams."
    assert ask_body["citations"]
    assert captured_request["url"] == "https://llm.example/v1/chat/completions"
    assert captured_request["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert captured_request["timeout"] == 30.0
    payload = captured_request["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "test-model"
    assert payload["temperature"] == 0
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Answer only from the provided retrieval context." in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "What does PureLink store?" in messages[1]["content"]
    assert "PureLink stores internal docs for teams." in messages[1]["content"]


@pytest.mark.anyio
async def test_personal_ask_creates_and_reuses_conversation_history(
    document_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        document_client,
        email="conversation-personal@example.com",
        username="conversation-personal",
    )
    bob = await _register_and_login(
        document_client,
        email="conversation-personal-other@example.com",
        username="conversation-personal-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    knowledge_base_id = await _create_personal_knowledge_base(
        document_client,
        access_token=str(alice["access_token"]),
        name="Conversation KB",
    )
    upload_response = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=alice_headers,
        files={"file": ("conversation.txt", b"PureLink stores internal docs for teams.", "text/plain")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    for action in ("parse", "chunk", "embed"):
        response = await document_client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/{action}",
            headers=alice_headers,
        )
        assert response.status_code == 200

    first_ask = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={"question": "What does PureLink store?"},
    )
    assert first_ask.status_code == 200
    first_body = first_ask.json()
    conversation_id = first_body["conversation_id"]
    assert isinstance(conversation_id, int)
    assert first_body["citations"]

    second_ask = await document_client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/ask",
        headers=alice_headers,
        json={
            "question": "Who is it for?",
            "conversation_id": conversation_id,
        },
    )
    assert second_ask.status_code == 200
    assert second_ask.json()["conversation_id"] == conversation_id

    list_response = await document_client.get(
        "/api/v1/conversations",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    conversations = list_response.json()
    assert len(conversations) == 1
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["knowledge_base_id"] == knowledge_base_id
    assert conversations[0]["scope"] == "personal"
    assert conversations[0]["team_id"] is None
    assert conversations[0]["title"] == "What does PureLink store?"

    detail_response = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=alice_headers,
    )
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["id"] == conversation_id
    assert detail_body["messages"][0]["role"] == "user"
    assert detail_body["messages"][0]["content"] == "What does PureLink store?"
    assert detail_body["messages"][1]["role"] == "assistant"
    assert detail_body["messages"][1]["citations"]
    assert detail_body["messages"][1]["citations"][0]["document_id"] == document_id
    assert detail_body["messages"][2]["role"] == "user"
    assert detail_body["messages"][2]["content"] == "Who is it for?"
    assert detail_body["messages"][3]["role"] == "assistant"

    other_user_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=bob_headers,
    )
    assert other_user_detail.status_code == 404


@pytest.mark.anyio
async def test_team_conversation_history_is_user_owned_and_team_scoped(
    document_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        document_client,
        email="conversation-team-admin@example.com",
        username="conversation-team-admin",
    )
    member = await _register_and_login(
        document_client,
        email="conversation-team-member@example.com",
        username="conversation-team-member",
    )
    outsider = await _register_and_login(
        document_client,
        email="conversation-team-outsider@example.com",
        username="conversation-team-outsider",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        document_client,
        access_token=str(admin["access_token"]),
        name="Conversation Team",
    )
    invite_code = await _create_team_invite(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        document_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    knowledge_base_id = await _create_team_knowledge_base(
        document_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
        name="Team Conversation KB",
    )

    upload_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents",
        headers=member_headers,
        files={"file": ("team-conversation.md", b"Team answers are shared after approval.", "text/markdown")},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["id"]

    approve_response = await document_client.post(
        f"/api/v1/teams/{team_id}/documents/{document_id}/approve",
        headers=admin_headers,
    )
    assert approve_response.status_code == 200

    for action in ("parse", "chunk", "embed"):
        response = await document_client.post(
            f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/{action}",
            headers=member_headers,
        )
        assert response.status_code == 200

    ask_response = await document_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask",
        headers=member_headers,
        json={"question": "What happens after approval?"},
    )
    assert ask_response.status_code == 200
    conversation_id = ask_response.json()["conversation_id"]

    member_list = await document_client.get(
        "/api/v1/conversations",
        headers=member_headers,
    )
    assert member_list.status_code == 200
    member_conversations = member_list.json()
    assert len(member_conversations) == 1
    assert member_conversations[0]["id"] == conversation_id
    assert member_conversations[0]["scope"] == "team"
    assert member_conversations[0]["team_id"] == team_id

    member_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=member_headers,
    )
    assert member_detail.status_code == 200
    member_messages = member_detail.json()["messages"]
    assert len(member_messages) == 2
    assert member_messages[1]["citations"]
    assert member_messages[1]["citations"][0]["document_id"] == document_id
    assert member_messages[1]["citations"][0]["team_id"] == team_id

    admin_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=admin_headers,
    )
    outsider_detail = await document_client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=outsider_headers,
    )
    assert admin_detail.status_code == 404
    assert outsider_detail.status_code == 404
