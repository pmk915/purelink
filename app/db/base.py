from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def load_all_models() -> None:
    from app.models.conversation import Conversation  # noqa: F401
    from app.models.document import Document  # noqa: F401
    from app.models.document_task import DocumentTask  # noqa: F401
    from app.models.knowledge_base import KnowledgeBase  # noqa: F401
    from app.models.message import Message  # noqa: F401
    from app.models.team import Team, TeamInvite, TeamMember  # noqa: F401
    from app.models.user import User  # noqa: F401
