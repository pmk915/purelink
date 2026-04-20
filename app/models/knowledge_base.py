from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import KnowledgeBaseScope, enum_values
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.document import Document
    from app.models.team import Team
    from app.models.user import User


class KnowledgeBase(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "("
            "(scope = 'personal' AND owner_id IS NOT NULL AND team_id IS NULL) "
            "OR "
            "(scope = 'team' AND owner_id IS NULL AND team_id IS NOT NULL)"
            ")",
            name="scope_owner_team_consistency",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[KnowledgeBaseScope] = mapped_column(
        SAEnum(
            KnowledgeBaseScope,
            name="knowledge_base_scope",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=KnowledgeBaseScope.PERSONAL,
        server_default=KnowledgeBaseScope.PERSONAL.value,
        nullable=False,
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )

    owner: Mapped["User | None"] = relationship(
        back_populates="knowledge_bases",
        foreign_keys=[owner_id],
    )
    team: Mapped["Team | None"] = relationship(back_populates="knowledge_bases")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="knowledge_base",
    )
