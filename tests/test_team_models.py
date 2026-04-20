from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
    TeamInviteStatus,
    TeamMemberRole,
    TeamMemberStatus,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.team import Team, TeamInvite, TeamMember
from app.models.user import User
from app.services.knowledge_base import create_knowledge_base


load_all_models()


def test_team_domain_models_support_personal_and_team_knowledge_bases() -> None:
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
        with testing_session_local() as db:
            alice = User(
                email="alice@example.com",
                username="alice",
                hashed_password="hashed",
                is_active=True,
            )
            bob = User(
                email="bob@example.com",
                username="bob",
                hashed_password="hashed",
                is_active=True,
            )
            db.add_all([alice, bob])
            db.commit()
            db.refresh(alice)
            db.refresh(bob)

            personal_kb = create_knowledge_base(
                db,
                owner_id=alice.id,
                name="Alice Personal KB",
                description="Personal scope remains the default.",
            )

            team = Team(
                name="Platform Team",
                description="Team collaboration base model.",
                created_by=alice.id,
            )
            db.add(team)
            db.commit()
            db.refresh(team)

            membership = TeamMember(
                team_id=team.id,
                user_id=alice.id,
                role=TeamMemberRole.ADMIN,
                status=TeamMemberStatus.ACTIVE,
                joined_at=datetime.now(UTC),
            )
            invite = TeamInvite(
                team_id=team.id,
                code="invite-platform-001",
                invited_by=alice.id,
                expires_at=datetime.now(UTC) + timedelta(days=7),
                status=TeamInviteStatus.ACTIVE,
            )
            team_kb = KnowledgeBase(
                name="Platform Shared KB",
                description="Team scoped knowledge base.",
                scope=KnowledgeBaseScope.TEAM,
                team_id=team.id,
            )
            db.add_all([membership, invite, team_kb])
            db.commit()
            db.refresh(team_kb)

            team_document = Document(
                knowledge_base_id=team_kb.id,
                owner_id=bob.id,
                submitted_by=bob.id,
                filename="architecture.txt",
                original_filename="architecture.txt",
                file_type="text/plain",
                file_size=128,
                storage_path="data/uploads/architecture.txt",
                review_status=DocumentReviewStatus.PENDING_REVIEW,
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
            db.add(team_document)
            db.commit()

            saved_team = db.scalar(select(Team).where(Team.id == team.id))
            saved_document = db.scalar(select(Document).where(Document.id == team_document.id))

            assert personal_kb.scope == KnowledgeBaseScope.PERSONAL
            assert personal_kb.owner_id == alice.id
            assert personal_kb.team_id is None

            assert team_kb.scope == KnowledgeBaseScope.TEAM
            assert team_kb.owner_id is None
            assert team_kb.team_id == team.id

            assert saved_team is not None
            assert len(saved_team.members) == 1
            assert saved_team.members[0].role == TeamMemberRole.ADMIN
            assert len(saved_team.invites) == 1
            assert len(saved_team.knowledge_bases) == 1

            assert saved_document is not None
            assert saved_document.review_status == DocumentReviewStatus.PENDING_REVIEW
            assert saved_document.processing_status == DocumentProcessingStatus.UPLOADED
            assert saved_document.submitted_by == bob.id
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
