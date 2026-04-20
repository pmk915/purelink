from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase
    from app.models.team import Team, TeamInvite, TeamMember


class User(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        foreign_keys="KnowledgeBase.owner_id",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        foreign_keys="Document.owner_id",
    )
    submitted_documents: Mapped[list["Document"]] = relationship(
        back_populates="submitted_by_user",
        foreign_keys="Document.submitted_by",
    )
    reviewed_documents: Mapped[list["Document"]] = relationship(
        back_populates="reviewed_by_user",
        foreign_keys="Document.reviewed_by",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    created_teams: Mapped[list["Team"]] = relationship(
        back_populates="creator",
        foreign_keys="Team.created_by",
    )
    team_memberships: Mapped[list["TeamMember"]] = relationship(
        back_populates="user",
        foreign_keys="TeamMember.user_id",
        cascade="all, delete-orphan",
    )
    sent_team_invites: Mapped[list["TeamInvite"]] = relationship(
        back_populates="inviter",
        foreign_keys="TeamInvite.invited_by",
    )
    used_team_invites: Mapped[list["TeamInvite"]] = relationship(
        back_populates="used_by_user",
        foreign_keys="TeamInvite.used_by",
    )
