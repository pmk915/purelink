from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.db.session import get_db
from app.main import app
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation


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
async def graph_client(test_session_factory: sessionmaker) -> AsyncClient:
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
async def test_personal_owner_can_run_graph_maintenance(
    graph_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    user = await _register_and_login(
        graph_client,
        email="personal-graph-owner@example.com",
        username="personal-graph-owner",
    )
    headers = {"Authorization": f"Bearer {user['access_token']}"}
    create_response = await graph_client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": "Personal Graph Maintenance"},
    )
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]

    with test_session_factory() as db:
        document_id = _seed_graph_document(
            db,
            kb_id=kb_id,
            user_id=int(user["user_id"]),
            review_status=DocumentReviewStatus.NOT_REQUIRED,
        )

    export_response = await graph_client.get(
        f"/api/v1/knowledge-bases/{kb_id}/graph/export",
        headers=headers,
    )
    cleanup_response = await graph_client.post(
        f"/api/v1/knowledge-bases/{kb_id}/graph/cleanup-orphans",
        headers=headers,
    )
    dedupe_response = await graph_client.post(
        f"/api/v1/knowledge-bases/{kb_id}/graph/deduplicate-relations",
        headers=headers,
    )
    rebuild_response = await graph_client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/graph/rebuild",
        headers=headers,
    )

    assert export_response.status_code == 200
    assert export_response.json()["relations"][0]["sources"][0]["filename"] == "graph.md"
    assert cleanup_response.status_code == 200
    assert "deleted_orphan_entities" in cleanup_response.json()
    assert dedupe_response.status_code == 200
    assert "deleted_duplicate_relations" in dedupe_response.json()
    assert rebuild_response.status_code == 200
    assert rebuild_response.json()["document_id"] == document_id
    assert rebuild_response.json()["created_mentions"] > 0


@pytest.mark.anyio
async def test_team_graph_maintenance_requires_admin_but_export_allows_member(
    graph_client: AsyncClient,
    test_session_factory: sessionmaker,
) -> None:
    admin = await _register_and_login(
        graph_client,
        email="team-graph-admin@example.com",
        username="team-graph-admin",
    )
    member = await _register_and_login(
        graph_client,
        email="team-graph-member@example.com",
        username="team-graph-member",
    )
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    team_id = await _create_team(
        graph_client,
        access_token=str(admin["access_token"]),
        name="Graph Team",
    )
    invite_code = await _create_team_invite(
        graph_client,
        access_token=str(admin["access_token"]),
        team_id=team_id,
    )
    await _join_team(
        graph_client,
        access_token=str(member["access_token"]),
        code=invite_code,
    )
    create_response = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases",
        headers=admin_headers,
        json={"name": "Team Graph Maintenance"},
    )
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]

    with test_session_factory() as db:
        document_id = _seed_graph_document(
            db,
            kb_id=kb_id,
            user_id=int(admin["user_id"]),
            review_status=DocumentReviewStatus.APPROVED,
        )

    member_export = await graph_client.get(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/export",
        headers=member_headers,
    )
    member_cleanup = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/cleanup-orphans",
        headers=member_headers,
    )
    member_dedupe = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/deduplicate-relations",
        headers=member_headers,
    )
    member_rebuild = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents/{document_id}/graph/rebuild",
        headers=member_headers,
    )
    admin_cleanup = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/cleanup-orphans",
        headers=admin_headers,
    )
    admin_dedupe = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/graph/deduplicate-relations",
        headers=admin_headers,
    )
    admin_rebuild = await graph_client.post(
        f"/api/v1/teams/{team_id}/knowledge-bases/{kb_id}/documents/{document_id}/graph/rebuild",
        headers=admin_headers,
    )

    assert member_export.status_code == 200
    assert member_export.json()["entities"]
    assert member_cleanup.status_code == 403
    assert member_dedupe.status_code == 403
    assert member_rebuild.status_code == 403
    assert admin_cleanup.status_code == 200
    assert admin_dedupe.status_code == 200
    assert admin_rebuild.status_code == 200


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


def _seed_graph_document(
    db: Session,
    *,
    kb_id: int,
    user_id: int,
    review_status: DocumentReviewStatus,
) -> int:
    document = Document(
        knowledge_base_id=kb_id,
        owner_id=user_id,
        submitted_by=user_id,
        filename="graph.md",
        original_filename="graph.md",
        file_type="text/markdown",
        file_size=64,
        storage_path=f"graph/{kb_id}/graph.md",
        review_status=review_status,
        processing_status=DocumentProcessingStatus.INDEXED,
    )
    db.add(document)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_key=f"document:{document.id}:chunk:0",
        chunk_index=0,
        chunk_text="管理员可以删除文档，普通成员可以上传文档。",
    )
    db.add(chunk)
    db.flush()
    unit = DocumentCitationUnit(
        document_id=document.id,
        chunk_id=chunk.id,
        knowledge_base_id=kb_id,
        chunk_key=chunk.chunk_key,
        unit_index=0,
        unit_text=chunk.chunk_text,
    )
    db.add(unit)
    db.flush()
    admin_entity = KnowledgeEntity(
        knowledge_base_id=kb_id,
        name="管理员",
        normalized_name="管理员",
        entity_type="role",
    )
    document_entity = KnowledgeEntity(
        knowledge_base_id=kb_id,
        name="文档",
        normalized_name="文档",
        entity_type="document",
    )
    db.add_all([admin_entity, document_entity])
    db.flush()
    db.add_all(
        [
            EntityMention(
                entity_id=admin_entity.id,
                knowledge_base_id=kb_id,
                document_id=document.id,
                chunk_id=chunk.id,
                citation_unit_id=unit.id,
                text_span="管理员",
            ),
            EntityMention(
                entity_id=document_entity.id,
                knowledge_base_id=kb_id,
                document_id=document.id,
                chunk_id=chunk.id,
                citation_unit_id=unit.id,
                text_span="文档",
            ),
            KnowledgeRelation(
                knowledge_base_id=kb_id,
                source_entity_id=admin_entity.id,
                target_entity_id=document_entity.id,
                relation_type="can_delete",
                source_document_id=document.id,
                source_chunk_id=chunk.id,
                source_citation_unit_id=unit.id,
            ),
        ]
    )
    db.commit()
    return document.id
