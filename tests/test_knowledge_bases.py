from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.document_block import DocumentBlock
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.document_index import DocumentIndex
from app.models.enums import (
    DocumentIndexStatus,
    DocumentIndexType,
    DocumentProcessingStatus,
    DocumentReviewStatus,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
)
from app.models.knowledge_graph import EntityMention, KnowledgeEntity
from app.models.processing_job import ProcessingJob
from app.schemas.document import RetrievalQueryRequest


load_all_models()


def test_retrieval_query_request_accepts_hybrid_text_mode() -> None:
    payload = RetrievalQueryRequest(
        query="/api/v1/knowledge-bases/{id}/rag-health",
        top_k=3,
        mode="hybrid_text",
    )

    assert payload.mode == "hybrid_text"


def test_retrieval_query_request_accepts_auto_mode() -> None:
    payload = RetrievalQueryRequest(
        query="CHUNK_STRATEGY 在哪里配置",
        top_k=3,
        mode="auto",
    )

    assert payload.mode == "auto"


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


@pytest.mark.anyio
async def test_personal_document_rag_debug_reports_retrieval_prerequisites(
    knowledge_base_client: AsyncClient,
    test_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hashed_bow")
    monkeypatch.setenv("EMBEDDING_MODEL", "")
    get_settings.cache_clear()
    alice = await _register_and_login(
        knowledge_base_client,
        email="rag-debug-owner@example.com",
        username="rag-debug-owner",
    )
    bob = await _register_and_login(
        knowledge_base_client,
        email="rag-debug-other@example.com",
        username="rag-debug-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    create_response = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=alice_headers,
        json={"name": "RAG Debug KB"},
    )
    knowledge_base_id = create_response.json()["id"]

    db = test_session_factory()
    try:
        document = Document(
            knowledge_base_id=knowledge_base_id,
            owner_id=int(alice["user_id"]),
            submitted_by=int(alice["user_id"]),
            filename="debug.txt",
            original_filename="debug.txt",
            file_type="txt",
            file_size=64,
            sha256="debug-doc",
            storage_path="uploads/debug.txt",
            review_status=DocumentReviewStatus.NOT_REQUIRED,
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        db.add(document)
        db.flush()
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_key=f"{document.id}:0",
            chunk_index=0,
            chunk_text="PureLink personal knowledge bases document retrieval citation smoke test.",
        )
        db.add(chunk)
        db.flush()
        db.add_all(
            [
                DocumentBlock(
                    document_id=document.id,
                    block_type="text",
                    text="PureLink personal knowledge bases.",
                    order_index=0,
                ),
                DocumentCitationUnit(
                    document_id=document.id,
                    knowledge_base_id=knowledge_base_id,
                    chunk_id=chunk.id,
                    chunk_key=chunk.chunk_key,
                    unit_index=0,
                    unit_text=chunk.chunk_text,
                    start_char=0,
                    end_char=len(chunk.chunk_text),
                ),
                DocumentIndex(
                    document_id=document.id,
                    knowledge_base_id=knowledge_base_id,
                    index_type=DocumentIndexType.VECTOR,
                    provider="local_hashed_bow",
                    model_name="hashed_bow_v1",
                    model_dim=128,
                    status=DocumentIndexStatus.INDEXED,
                ),
                ProcessingJob(
                    document_id=document.id,
                    triggered_by_id=int(alice["user_id"]),
                    job_type=ProcessingJobType.DOCUMENT_INDEX,
                    trigger_type=ProcessingJobTrigger.INDEX,
                    status=ProcessingJobStatus.SUCCEEDED,
                    current_step="finalize_index",
                ),
            ]
        )
        db.commit()
        document_id = document.id
    finally:
        db.close()

    forbidden = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/rag-debug",
        headers=bob_headers,
    )
    assert forbidden.status_code == 404

    response = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/rag-debug",
        headers=alice_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    assert body["chunk_count"] == 1
    assert body["citation_unit_count"] == 1
    assert body["block_count"] == 1
    assert body["vector_index"]["status"] == "indexed"
    assert body["vector_index"]["compatible"] is True
    assert body["latest_processing_job"]["status"] == "succeeded"
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_personal_graph_entities_are_owner_visible(
    knowledge_base_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    alice = await _register_and_login(
        knowledge_base_client,
        email="graph-owner@example.com",
        username="graph-owner",
    )
    bob = await _register_and_login(
        knowledge_base_client,
        email="graph-other@example.com",
        username="graph-other",
    )
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    create_response = await knowledge_base_client.post(
        "/api/v1/knowledge-bases",
        headers=alice_headers,
        json={"name": "Graph KB"},
    )
    assert create_response.status_code == 201
    knowledge_base_id = create_response.json()["id"]

    db = test_session_factory()
    try:
        document = Document(
            knowledge_base_id=knowledge_base_id,
            owner_id=int(alice["user_id"]),
            submitted_by=int(alice["user_id"]),
            filename="graph.txt",
            original_filename="graph.txt",
            file_type="txt",
            file_size=12,
            sha256="graph-doc",
            storage_path="uploads/graph.txt",
            review_status=DocumentReviewStatus.NOT_REQUIRED,
            processing_status=DocumentProcessingStatus.INDEXED,
        )
        entity = KnowledgeEntity(
            knowledge_base_id=knowledge_base_id,
            name="Retrieval Layer",
            normalized_name="retrieval layer",
            entity_type="concept",
        )
        db.add_all([document, entity])
        db.flush()
        db.add(
            EntityMention(
                entity_id=entity.id,
                knowledge_base_id=knowledge_base_id,
                document_id=document.id,
                text_span="Retrieval Layer",
                source_locator="section: M1",
            )
        )
        db.commit()
        entity_id = entity.id
    finally:
        db.close()

    list_response = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/graph/entities?q=retrieval",
        headers=alice_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["name"] == "Retrieval Layer"
    assert list_response.json()["items"][0]["mention_count"] == 1

    detail_response = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/graph/entities/{entity_id}",
        headers=alice_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["mentions"][0]["source_locator"] == "section: M1"

    other_response = await knowledge_base_client.get(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/graph/entities",
        headers=bob_headers,
    )
    assert other_response.status_code == 404
