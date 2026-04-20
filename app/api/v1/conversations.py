from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession
from app.schemas.conversation import (
    ConversationMessageRead,
    ConversationRead,
    ConversationSummaryRead,
)
from app.services.conversation import (
    deserialize_citations,
    get_accessible_conversation_for_user,
    list_accessible_conversations_for_user,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummaryRead])
async def list_conversations_endpoint(
    db: DBSession,
    current_user: CurrentUser,
) -> list[ConversationSummaryRead]:
    conversations = list_accessible_conversations_for_user(
        db,
        user_id=current_user.id,
    )
    return [_build_conversation_summary(item) for item in conversations]


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation_endpoint(
    conversation_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ConversationRead:
    conversation = get_accessible_conversation_for_user(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        include_messages=True,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return ConversationRead(
        **_build_conversation_summary(conversation).model_dump(),
        messages=[
            ConversationMessageRead(
                id=item.id,
                role=item.role,
                content=item.content,
                citations=deserialize_citations(item),
                created_at=item.created_at,
            )
            for item in conversation.messages
        ],
    )


def _build_conversation_summary(conversation) -> ConversationSummaryRead:
    knowledge_base = conversation.knowledge_base
    return ConversationSummaryRead(
        id=conversation.id,
        knowledge_base_id=conversation.knowledge_base_id,
        title=conversation.title,
        scope=knowledge_base.scope.value,
        team_id=knowledge_base.team_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )
