from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.document_index import DocumentIndex
from app.models.enums import DocumentIndexStatus, DocumentIndexType, DocumentProcessingStatus, DocumentReviewStatus


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
async def knowledge_base_client(test_session_factory: sessionmaker) -> AsyncClient:
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
async def test_knowledge_base_endpoints_require_authentication(
    knowledge_base_client: AsyncClient,
) -> None:
    list_response = await knowledge_base_client.get("/api/v1/knowledge-bases")
    create_response = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Unauthorized KB"},
    )

    assert list_response.status_code == 401
    assert create_response.status_code == 401


@pytest.mark.anyio
async def test_create_and_list_only_current_users_knowledge_bases(
    knowledge_base_client: AsyncClient,
) -> None:
    alice = await _register_and_login(
        knowledge_base_client,
        email="alice@example.com",
        username="alice",
    )
    bob = await _register_and_login(
        knowledge_base_client,
        email="bob@example.com",
        username="bob",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    create_first = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=alice_headers,
        json={
            "name": "Alice KB 1",
            "description": "First knowledge base",
        },
    )
    create_second = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=alice_headers,
        json={
            "name": "Alice KB 2",
            "description": "Second knowledge base",
        },
    )
    create_bob = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=bob_headers,
        json={
            "name": "Bob KB",
            "description": "Bob knowledge base",
        },
    )

    assert create_first.status_code == 201
    assert create_second.status_code == 201
    assert create_bob.status_code == 201
    assert create_first.json()["scope"] == "personal"
    assert create_first.json()["team_id"] is None
    assert create_first.json()["owner_id"] == alice["user_id"]
    assert create_bob.json()["scope"] == "personal"
    assert create_bob.json()["team_id"] is None
    assert create_bob.json()["owner_id"] == bob["user_id"]

    response = await knowledge_base_client.get(
        "/api/v1/knowledge-bases",
        headers=alice_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {item["name"] for item in body} == {"Alice KB 1", "Alice KB 2"}
    assert {item["scope"] for item in body} == {"personal"}
    assert {item["team_id"] for item in body} == {None}
    assert {item["owner_id"] for item in body} == {alice["user_id"]}


@pytest.mark.anyio
async def test_knowledge_base_detail_update_delete_enforce_ownership(
    knowledge_base_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        knowledge_base_client,
        email="owner@example.com",
        username="owner",
    )
    bob = await _register_and_login(
        knowledge_base_client,
        email="other@example.com",
        username="other",
    )

    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    create_response = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=alice_headers,
        json={
            "name": "Private KB",
            "description": "Owner only",
        },
    )
    knowledge_base_id = create_response.json()["id"]

    db = test_session_factory()
    try:
        document = Document(
            knowledge_base_id=knowledge_base_id,
            owner_id=int(alice["user_id"]),
            submitted_by=int(alice["user_id"]),
            filename="health.txt",
            original_filename="health.txt",
            file_type="txt",
            file_size=12,
            sha256="health-doc",
            storage_path="uploads/health.txt",
            review_status=DocumentReviewStatus.NOT_REQUIRED,
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentIndex(
                document_id=document.id,
                knowledge_base_id=knowledge_base_id,
                index_type=DocumentIndexType.VECTOR,
                provider="local",
                model_name="test",
                model_dim=3,
                status=DocumentIndexStatus.INDEXED,
            )
        )
        db.commit()
    finally:
        db.close()

    get_other = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=bob_headers,
    )
    health_other = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/rag-health",
        headers=bob_headers,
    )
    update_other = await knowledge_base_client.patch(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=bob_headers,
        json={"name": "Should Not Work"},
    )
    delete_other = await knowledge_base_client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=bob_headers,
    )

    assert get_other.status_code == 404
    assert health_other.status_code == 404
    assert update_other.status_code == 404
    assert delete_other.status_code == 404

    get_owner = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=alice_headers,
    )
    assert get_owner.status_code == 200
    assert get_owner.json()["name"] == "Private KB"
    assert get_owner.json()["scope"] == "personal"
    assert get_owner.json()["team_id"] is None

    update_owner = await knowledge_base_client.patch(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=alice_headers,
        json={
            "name": "Renamed KB",
            "description": "Updated description",
        },
    )
    assert update_owner.status_code == 200
    assert update_owner.json()["name"] == "Renamed KB"
    assert update_owner.json()["description"] == "Updated description"
    assert update_owner.json()["scope"] == "personal"
    assert update_owner.json()["team_id"] is None

    health_owner = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/rag-health",
        headers=alice_headers,
    )
    assert health_owner.status_code == 200
    assert health_owner.json() == {
        "document_count": 1,
        "document_status_counts": {"indexed": 1},
        "index_status_counts": {
            "vector": {"indexed": 1, "missing": 0},
            "graph": {"missing": 1},
        },
    }

    delete_owner = await knowledge_base_client.delete(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=alice_headers,
    )
    assert delete_owner.status_code == 204

    get_after_delete = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}",
        headers=alice_headers,
    )
    assert get_after_delete.status_code == 404
