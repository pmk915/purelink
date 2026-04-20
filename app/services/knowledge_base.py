from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase

UNSET: Any = object()


def create_knowledge_base(
    db: Session,
    *,
    owner_id: int,
    name: str,
    description: str | None,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        name=name,
        description=description,
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=owner_id,
    )
    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


def list_knowledge_bases_for_user(db: Session, *, owner_id: int) -> list[KnowledgeBase]:
    statement = (
        select(KnowledgeBase)
        .where(
            KnowledgeBase.scope == KnowledgeBaseScope.PERSONAL,
            KnowledgeBase.owner_id == owner_id,
        )
        .order_by(KnowledgeBase.created_at.desc(), KnowledgeBase.id.desc())
    )
    return list(db.scalars(statement))


def create_team_knowledge_base(
    db: Session,
    *,
    team_id: int,
    name: str,
    description: str | None,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        name=name,
        description=description,
        scope=KnowledgeBaseScope.TEAM,
        team_id=team_id,
    )
    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


def list_team_knowledge_bases(db: Session, *, team_id: int) -> list[KnowledgeBase]:
    statement = (
        select(KnowledgeBase)
        .where(
            KnowledgeBase.scope == KnowledgeBaseScope.TEAM,
            KnowledgeBase.team_id == team_id,
        )
        .order_by(KnowledgeBase.created_at.desc(), KnowledgeBase.id.desc())
    )
    return list(db.scalars(statement))


def get_knowledge_base_for_user(
    db: Session,
    *,
    owner_id: int,
    knowledge_base_id: int,
) -> KnowledgeBase | None:
    statement = select(KnowledgeBase).where(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.scope == KnowledgeBaseScope.PERSONAL,
        KnowledgeBase.owner_id == owner_id,
    )
    return db.scalar(statement)


def get_team_knowledge_base(
    db: Session,
    *,
    team_id: int,
    knowledge_base_id: int,
) -> KnowledgeBase | None:
    statement = select(KnowledgeBase).where(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.scope == KnowledgeBaseScope.TEAM,
        KnowledgeBase.team_id == team_id,
    )
    return db.scalar(statement)


def update_knowledge_base(
    db: Session,
    *,
    knowledge_base: KnowledgeBase,
    name: str | None = None,
    description: str | None | Any = UNSET,
) -> KnowledgeBase:
    if name is not None:
        knowledge_base.name = name

    if description is not UNSET:
        knowledge_base.description = description

    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


def delete_knowledge_base(db: Session, *, knowledge_base: KnowledgeBase) -> None:
    db.delete(knowledge_base)
    db.commit()
