from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.conversation import Conversation
from app.models.enums import KnowledgeBaseScope, MessageRole, TeamMemberStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.team import TeamMember
from app.schemas.qa import CitationRead


class ConversationNotFoundError(LookupError):
    pass


class ConversationKnowledgeBaseMismatchError(ValueError):
    pass


def list_accessible_conversations_for_user(
    db: Session,
    *,
    user_id: int,
) -> list[Conversation]:
    statement = (
        _accessible_conversation_statement(user_id=user_id, include_messages=False)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return list(db.execute(statement).scalars())


def get_accessible_conversation_for_user(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    include_messages: bool,
) -> Conversation | None:
    statement = _accessible_conversation_statement(
        user_id=user_id,
        include_messages=include_messages,
    ).where(Conversation.id == conversation_id)
    return db.scalar(statement)


def get_or_create_conversation_for_question(
    db: Session,
    *,
    user_id: int,
    knowledge_base_id: int,
    question: str,
    conversation_id: int | None,
) -> Conversation:
    if conversation_id is None:
        conversation = Conversation(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            title=build_conversation_title(question),
        )
        db.add(conversation)
        db.flush()
        return conversation

    conversation = get_accessible_conversation_for_user(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        include_messages=False,
    )
    if conversation is None:
        raise ConversationNotFoundError("Conversation not found.")
    if conversation.knowledge_base_id != knowledge_base_id:
        raise ConversationKnowledgeBaseMismatchError(
            "Conversation is not associated with this knowledge base."
        )
    return conversation


def persist_question_answer_exchange(
    db: Session,
    *,
    conversation: Conversation,
    question: str,
    answer: str,
    citations: list[CitationRead],
) -> tuple[Message, Message]:
    conversation.updated_at = datetime.now(UTC)

    question_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=question,
    )
    answer_message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=answer,
        citations_json=serialize_citations(citations),
    )
    db.add(question_message)
    db.add(answer_message)
    db.commit()
    db.refresh(conversation)
    db.refresh(question_message)
    db.refresh(answer_message)
    return question_message, answer_message


def deserialize_citations(message: Message) -> list[CitationRead]:
    if not message.citations_json:
        return []

    try:
        payload = json.loads(message.citations_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    citations: list[CitationRead] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            citations.append(CitationRead.model_validate(item))
        except Exception:
            continue
    return citations


def build_conversation_title(question: str, *, max_length: int = 120) -> str:
    normalized = " ".join(question.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def serialize_citations(citations: list[CitationRead]) -> str | None:
    if not citations:
        return None
    return json.dumps(
        [item.model_dump() for item in citations],
        ensure_ascii=False,
    )


def _accessible_conversation_statement(
    *,
    user_id: int,
    include_messages: bool,
):
    statement = (
        select(Conversation)
        .join(KnowledgeBase, KnowledgeBase.id == Conversation.knowledge_base_id)
        .outerjoin(
            TeamMember,
            and_(
                TeamMember.team_id == KnowledgeBase.team_id,
                TeamMember.user_id == user_id,
                TeamMember.status == TeamMemberStatus.ACTIVE,
            ),
        )
        .options(selectinload(Conversation.knowledge_base))
        .where(
            Conversation.user_id == user_id,
            or_(
                and_(
                    KnowledgeBase.scope == KnowledgeBaseScope.PERSONAL,
                    KnowledgeBase.owner_id == user_id,
                ),
                and_(
                    KnowledgeBase.scope == KnowledgeBaseScope.TEAM,
                    TeamMember.id.is_not(None),
                ),
            ),
        )
    )
    if include_messages:
        statement = statement.options(selectinload(Conversation.messages))
    return statement
