from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.enums import TeamInviteStatus
from app.models.team import TeamInvite


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
async def team_client(test_session_factory: sessionmaker) -> AsyncClient:
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


@pytest.mark.anyio
async def test_team_endpoints_require_authentication(team_client: AsyncClient) -> None:
    list_response = await team_client.get("/api/v1/teams")
    create_response = await team_client.post(
        "/api/v1/teams",
        json={"name": "Unauthorized Team"},
    )
    join_response = await team_client.post(
        "/api/v1/team-invites/join",
        json={"code": "nope"},
    )

    assert list_response.status_code == 401
    assert create_response.status_code == 401
    assert join_response.status_code == 401


@pytest.mark.anyio
async def test_create_team_lists_team_and_bootstraps_admin_membership(
    team_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        team_client,
        email="alice-team@example.com",
        username="alice-team",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}

    create_response = await team_client.post(
        "/api/v1/teams",
        headers=alice_headers,
        json={
            "name": "Platform Team",
            "description": "Core collaboration team.",
        },
    )

    assert create_response.status_code == 201
    team_body = create_response.json()
    team_id = team_body["id"]
    assert team_body["name"] == "Platform Team"
    assert team_body["created_by"] == alice["user_id"]
    assert team_body["my_role"] == "admin"
    assert team_body["my_status"] == "active"

    list_response = await team_client.get("/api/v1/teams", headers=alice_headers)
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["id"] == team_id
    assert listed[0]["my_role"] == "admin"

    detail_response = await team_client.get(
        f"/api/v1/teams/{team_id}",
        headers=alice_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == team_id

    members_response = await team_client.get(
        f"/api/v1/teams/{team_id}/members",
        headers=alice_headers,
    )
    assert members_response.status_code == 200
    members = members_response.json()
    assert len(members) == 1
    assert members[0]["role"] == "admin"
    assert members[0]["user"]["email"] == "alice-team@example.com"


@pytest.mark.anyio
async def test_admin_can_invite_member_and_member_permissions_are_limited(
    team_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        team_client,
        email="owner-team@example.com",
        username="owner-team",
    )
    bob = await _register_and_login(
        team_client,
        email="member-team@example.com",
        username="member-team",
    )
    outsider = await _register_and_login(
        team_client,
        email="outsider-team@example.com",
        username="outsider-team",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    outsider_headers = {"Authorization": f"Bearer {outsider['access_token']}"}

    create_team_response = await team_client.post(
        "/api/v1/teams",
        headers=alice_headers,
        json={"name": "Docs Team", "description": "Shared docs"},
    )
    team_id = create_team_response.json()["id"]

    outsider_detail = await team_client.get(
        f"/api/v1/teams/{team_id}",
        headers=outsider_headers,
    )
    outsider_members = await team_client.get(
        f"/api/v1/teams/{team_id}/members",
        headers=outsider_headers,
    )
    assert outsider_detail.status_code == 404
    assert outsider_members.status_code == 404

    create_invite_response = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )
    assert create_invite_response.status_code == 201
    invite_body = create_invite_response.json()
    assert invite_body["team_id"] == team_id
    assert invite_body["status"] == "active"

    invite_list_response = await team_client.get(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
    )
    assert invite_list_response.status_code == 200
    assert len(invite_list_response.json()) == 1

    join_response = await team_client.post(
        "/api/v1/team-invites/join",
        headers=bob_headers,
        json={"code": invite_body["code"]},
    )
    assert join_response.status_code == 200
    assert join_response.json()["id"] == team_id
    assert join_response.json()["my_role"] == "member"
    assert join_response.json()["my_status"] == "active"

    member_detail = await team_client.get(
        f"/api/v1/teams/{team_id}",
        headers=bob_headers,
    )
    assert member_detail.status_code == 200

    member_members = await team_client.get(
        f"/api/v1/teams/{team_id}/members",
        headers=bob_headers,
    )
    assert member_members.status_code == 200
    members = member_members.json()
    assert len(members) == 2
    assert {item["user"]["email"] for item in members} == {
        "owner-team@example.com",
        "member-team@example.com",
    }

    member_create_invite = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=bob_headers,
        json={"expires_in_days": 7},
    )
    member_list_invites = await team_client.get(
        f"/api/v1/teams/{team_id}/invites",
        headers=bob_headers,
    )
    assert member_create_invite.status_code == 403
    assert member_list_invites.status_code == 403


@pytest.mark.anyio
async def test_join_validates_invite_expiry_status_and_duplicate_membership(
    team_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        team_client,
        email="expiry-owner@example.com",
        username="expiry-owner",
    )
    bob = await _register_and_login(
        team_client,
        email="expiry-member@example.com",
        username="expiry-member",
    )
    charlie = await _register_and_login(
        team_client,
        email="expiry-other@example.com",
        username="expiry-other",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    charlie_headers = {"Authorization": f"Bearer {charlie['access_token']}"}

    create_team_response = await team_client.post(
        "/api/v1/teams",
        headers=alice_headers,
        json={"name": "Review Team"},
    )
    team_id = create_team_response.json()["id"]

    missing_invite = await team_client.post(
        "/api/v1/team-invites/join",
        headers=charlie_headers,
        json={"code": "missing-invite-code"},
    )
    assert missing_invite.status_code == 404

    first_invite = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )
    first_code = first_invite.json()["code"]

    join_first = await team_client.post(
        "/api/v1/team-invites/join",
        headers=bob_headers,
        json={"code": first_code},
    )
    assert join_first.status_code == 200

    reuse_used_invite = await team_client.post(
        "/api/v1/team-invites/join",
        headers=charlie_headers,
        json={"code": first_code},
    )
    assert reuse_used_invite.status_code == 400

    second_invite = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )
    second_code = second_invite.json()["code"]

    duplicate_join = await team_client.post(
        "/api/v1/team-invites/join",
        headers=bob_headers,
        json={"code": second_code},
    )
    assert duplicate_join.status_code == 409

    third_invite = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )
    third_code = third_invite.json()["code"]

    with test_session_factory() as db:
        invite = db.scalar(select(TeamInvite).where(TeamInvite.code == third_code))
        assert invite is not None
        invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    expired_join = await team_client.post(
        "/api/v1/team-invites/join",
        headers=charlie_headers,
        json={"code": third_code},
    )
    assert expired_join.status_code == 400

    with test_session_factory() as db:
        expired_invite = db.scalar(select(TeamInvite).where(TeamInvite.code == third_code))
        assert expired_invite is not None
        assert expired_invite.status == TeamInviteStatus.EXPIRED


@pytest.mark.anyio
async def test_invite_list_hides_expired_and_inactive_codes(
    team_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        team_client,
        email="invite-list-owner@example.com",
        username="invite-list-owner",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    create_team_response = await team_client.post(
        "/api/v1/teams",
        headers=alice_headers,
        json={"name": "Invite Visibility Team"},
    )
    team_id = create_team_response.json()["id"]

    active_response = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )
    expired_response = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )
    revoked_response = await team_client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
        json={"expires_in_days": 7},
    )

    active_code = active_response.json()["code"]
    expired_code = expired_response.json()["code"]
    revoked_code = revoked_response.json()["code"]

    with test_session_factory() as db:
        expired_invite = db.scalar(select(TeamInvite).where(TeamInvite.code == expired_code))
        revoked_invite = db.scalar(select(TeamInvite).where(TeamInvite.code == revoked_code))
        assert expired_invite is not None
        assert revoked_invite is not None
        expired_invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        revoked_invite.status = TeamInviteStatus.REVOKED
        db.commit()

    list_response = await team_client.get(
        f"/api/v1/teams/{team_id}/invites",
        headers=alice_headers,
    )

    assert list_response.status_code == 200
    invites = list_response.json()
    assert [item["code"] for item in invites] == [active_code]

    with test_session_factory() as db:
        expired_invite = db.scalar(select(TeamInvite).where(TeamInvite.code == expired_code))
        assert expired_invite is not None
        assert expired_invite.status == TeamInviteStatus.EXPIRED
