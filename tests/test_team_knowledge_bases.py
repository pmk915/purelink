from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app


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
async def team_knowledge_base_client(test_session_factory: sessionmaker) -> AsyncClient:
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


@pytest.mark.anyio
async def test_team_knowledge_base_endpoints_require_authentication(
    team_knowledge_base_client: AsyncClient,
) -> None:
    list_response = await team_knowledge_base_client.get("/api/v1/teams/1/knowledge-bases")
    create_response = await team_knowledge_base_client.post(
        "/api/v1/teams/1/knowledge-bases",
        json={"name": "Unauthorized Team KB"},
    )
    detail_response = await team_knowledge_base_client.get(
        "/api/v1/teams/1/knowledge-bases/1"
    )

    assert list_response.status_code == 401
    assert create_response.status_code == 401
    assert detail_response.status_code == 401


@pytest.mark.anyio
async def test_team_knowledge_base_permissions_for_admin_member_and_non_member(
    team_knowledge_base_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        team_knowledge_base_client,
        email="team-kb-admin@example.com",
        username="team-kb-admin",
    )
    member = await _register_and_login(
        team_knowledge_base_client,
        email="team-kb-member@example.com",
        username="team-kb-member",
    )
    outsider = await _register_and_login(
        team_knowledge_base_client,
        email="team-kb-outsider@example.com",
        username="team-kb-outsider",
    )

    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    team_id = await _create_team(
        team_knowledge_base_client,
        access_token=str(admin["access_token"]),
        name="Docs Admin Team",
    )
    invite_code = await _create_team_invite(
        team_knowledge_base_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        team_knowledge_base_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )

    create_response = await team_knowledge_base_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=admin_headers,
        json={
            "name": "Shared Engineering Docs",
            "description": "Team knowledge base",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    knowledge_base_id = created["id"]
    assert created["scope"] == "team"
    assert created["team_id"] == team_id
    assert created["owner_id"] is None

    admin_list = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=admin_headers,
    )
    member_list = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=member_headers,
    )
    outsider_list = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=outsider_headers,
    )

    assert admin_list.status_code == 200
    assert member_list.status_code == 200
    assert outsider_list.status_code == 404
    assert len(admin_list.json()) == 1
    assert len(member_list.json()) == 1
    assert member_list.json()[0]["id"] == knowledge_base_id

    member_detail = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=member_headers,
    )
    outsider_detail = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=outsider_headers,
    )
    assert member_detail.status_code == 200
    assert outsider_detail.status_code == 404

    member_create = await team_knowledge_base_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=member_headers,
        json={"name": "Should Fail"},
    )
    member_update = await team_knowledge_base_client.patch(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=member_headers,
        json={"name": "Still Should Fail"},
    )
    member_delete = await team_knowledge_base_client.delete(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=member_headers,
    )

    assert member_create.status_code == 403
    assert member_update.status_code == 403
    assert member_delete.status_code == 403

    admin_update = await team_knowledge_base_client.patch(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=admin_headers,
        json={
            "name": "Updated Shared Docs",
            "description": "Updated by admin",
        },
    )
    assert admin_update.status_code == 200
    assert admin_update.json()["name"] == "Updated Shared Docs"

    admin_delete = await team_knowledge_base_client.delete(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=admin_headers,
    )
    assert admin_delete.status_code == 204

    after_delete = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}",
        headers=admin_headers,
    )
    assert after_delete.status_code == 404


@pytest.mark.anyio
async def test_personal_and_team_knowledge_base_interfaces_remain_separated(
    team_knowledge_base_client: AsyncClient,
) -> None:
    admin = await _register_and_login(
        team_knowledge_base_client,
        email="hybrid-owner@example.com",
        username="hybrid-owner",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}

    team_id = await _create_team(
        team_knowledge_base_client,
        access_token=str(admin["access_token"]),
        name="Hybrid Team",
    )

    personal_create = await team_knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=admin_headers,
        json={
            "name": "My Personal KB",
            "description": "Private notes",
        },
    )
    team_create = await team_knowledge_base_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=admin_headers,
        json={
            "name": "Team Shared KB",
            "description": "Shared notes",
        },
    )

    assert personal_create.status_code == 201
    assert team_create.status_code == 201

    personal_id = personal_create.json()["id"]
    team_kb_id = team_create.json()["id"]

    personal_list = await team_knowledge_base_client.get(
        "/api/v1/knowledge-bases",
        headers=admin_headers,
    )
    team_list = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=admin_headers,
    )

    assert personal_list.status_code == 200
    assert team_list.status_code == 200
    assert [item["id"] for item in personal_list.json()] == [personal_id]
    assert [item["id"] for item in team_list.json()] == [team_kb_id]
    assert personal_list.json()[0]["scope"] == "personal"
    assert team_list.json()[0]["scope"] == "team"

    personal_detail_for_team_kb = await team_knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{team_kb_id}",
        headers=admin_headers,
    )
    team_detail_for_personal_kb = await team_knowledge_base_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{personal_id}",
        headers=admin_headers,
    )

    assert personal_detail_for_team_kb.status_code == 404
    assert team_detail_for_personal_kb.status_code == 404
