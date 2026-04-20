from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.user import User


load_all_models()


@pytest.fixture
def test_session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
async def auth_client(test_session_factory: sessionmaker) -> AsyncClient:
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


@pytest.mark.anyio
async def test_register_user_hashes_password(
    auth_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    payload = {
        "email": "tester@example.com",
        "username": "tester",
        "password": "StrongPass123",
    }

    response = await auth_client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == payload["email"]
    assert body["username"] == payload["username"]
    assert "hashed_password" not in body

    with test_session_factory() as db:
        user = db.scalar(select(User).where(User.email == payload["email"]))

    assert user is not None
    assert user.hashed_password != payload["password"]

    duplicate = await auth_client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409


@pytest.mark.anyio
async def test_login_returns_bearer_token(auth_client: AsyncClient) -> None:
    register_payload = {
        "email": "login@example.com",
        "username": "loginuser",
        "password": "StrongPass123",
    }
    await auth_client.post("/api/v1/auth/register", json=register_payload)

    response = await auth_client.post(
        "/api/v1/auth/login",
        json={
            "identifier": register_payload["email"],
            "password": register_payload["password"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["access_token"]


@pytest.mark.anyio
async def test_read_current_user_requires_valid_token(auth_client: AsyncClient) -> None:
    register_payload = {
        "email": "me@example.com",
        "username": "meuser",
        "password": "StrongPass123",
    }
    await auth_client.post("/api/v1/auth/register", json=register_payload)

    login_response = await auth_client.post(
        "/api/v1/auth/login",
        json={
            "identifier": register_payload["username"],
            "password": register_payload["password"],
        },
    )
    token = login_response.json()["access_token"]

    response = await auth_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == register_payload["email"]
    assert body["username"] == register_payload["username"]
