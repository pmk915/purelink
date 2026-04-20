from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import TeamInviteStatus, TeamMemberRole, TeamMemberStatus, enum_values
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User


class Team(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    creator: Mapped["User"] = relationship(
        back_populates="created_teams",
        foreign_keys=[created_by],
    )
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )
    invites: Mapped[list["TeamInvite"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMember(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_id_user_id"),
    )

    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[TeamMemberRole] = mapped_column(
        SAEnum(
            TeamMemberRole,
            name="team_member_role",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    status: Mapped[TeamMemberStatus] = mapped_column(
        SAEnum(
            TeamMemberStatus,
            name="team_member_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(
        back_populates="team_memberships",
        foreign_keys=[user_id],
    )


class TeamInvite(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "team_invites"

    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    invited_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[TeamInviteStatus] = mapped_column(
        SAEnum(
            TeamInviteStatus,
            name="team_invite_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        nullable=False,
    )

    team: Mapped["Team"] = relationship(back_populates="invites")
    inviter: Mapped["User"] = relationship(
        back_populates="sent_team_invites",
        foreign_keys=[invited_by],
    )
    used_by_user: Mapped["User | None"] = relationship(
        back_populates="used_team_invites",
        foreign_keys=[used_by],
    )
