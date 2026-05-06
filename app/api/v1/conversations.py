from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DBSession
from app.core.config import BASE_DIR, get_settings
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.schemas.conversation import (
    AppendConversationMessageResponse,
    ConversationMessageCreateRequest,
    ConversationRead,
    ConversationSummaryRead,
)
from app.services.conversation import (
    build_conversation_message_read,
    delete_conversation,
    get_accessible_conversation_for_user,
    get_recent_conversation_messages,
    list_accessible_conversations_for_user,
    persist_question_answer_exchange,
)
from app.services.document import list_documents_for_knowledge_base
from app.services.document_embedding import DocumentEmbeddingError
from app.services.document_embedding import resolve_vector_store_root
from app.services.qa import (
    AnswerGenerationError,
    answer_question,
    build_conversation_context,
    build_conversation_retrieval_query,
)
from app.services.qa_intent import QAIntent, classify_qa_intent
from app.services.retrieval import retrieve_chunks_for_documents


router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger("purelink.conversations")


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
            build_conversation_message_read(item)
            for item in conversation.messages
        ],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conversation_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    conversation = get_accessible_conversation_for_user(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        include_messages=False,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    delete_conversation(db, conversation=conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=AppendConversationMessageResponse,
)
async def append_conversation_message_endpoint(
    conversation_id: int,
    payload: ConversationMessageCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> AppendConversationMessageResponse:
    conversation = get_accessible_conversation_for_user(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        include_messages=False,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    knowledge_base = conversation.knowledge_base
    if knowledge_base is None or conversation.knowledge_base_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is not associated with a knowledge base.",
        )

    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=conversation.knowledge_base_id,
    )
    settings = get_settings()
    recent_messages = get_recent_conversation_messages(
        db,
        conversation_id=conversation.id,
        limit=settings.conversation_recent_messages_limit,
    )
    conversation_context = build_conversation_context(
        messages=recent_messages,
        max_total_chars=settings.conversation_context_max_chars,
        max_message_chars=settings.conversation_message_max_chars,
    )
    retrieval_query = build_conversation_retrieval_query(
        question=payload.content,
        recent_messages=conversation_context,
    )

    scope = knowledge_base.scope
    required_review_status = (
        DocumentReviewStatus.APPROVED
        if scope == KnowledgeBaseScope.TEAM
        else DocumentReviewStatus.NOT_REQUIRED
    )
    team_id = knowledge_base.team_id if scope == KnowledgeBaseScope.TEAM else None
    intent = classify_qa_intent(payload.content)

    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    retrieved_chunks = []
    if intent == QAIntent.KB_FACT_QA:
        try:
            retrieved_chunks = retrieve_chunks_for_documents(
                db=db,
                documents=documents,
                vector_root=vector_root,
                scope=scope,
                knowledge_base_id=knowledge_base.id,
                team_id=team_id,
                query=retrieval_query,
                top_k=5,
                required_review_status=required_review_status,
            )
        except DocumentEmbeddingError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    try:
        qa_result = answer_question(
            db=db,
            question=payload.content,
            retrieved_chunks=retrieved_chunks,
            documents=documents,
            knowledge_base_id=knowledge_base.id,
            scope=scope,
            required_review_status=required_review_status,
            team_id=team_id,
            conversation_context=conversation_context,
            retrieval_query=retrieval_query,
            settings=settings,
        )
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    logger.info(
        "conversation message appended conversation_id=%s knowledge_base_id=%s qa_intent=%s recent_message_count=%s retrieval_query_length=%s citation_count=%s",
        conversation.id,
        knowledge_base.id,
        qa_result.intent,
        len(conversation_context),
        len(retrieval_query),
        len(qa_result.citations),
    )

    user_message, assistant_message = persist_question_answer_exchange(
        db,
        conversation=conversation,
        question=payload.content,
        answer=qa_result.answer,
        citations=qa_result.citations,
    )
    return AppendConversationMessageResponse(
        conversation=_build_conversation_summary(conversation),
        user_message=build_conversation_message_read(user_message),
        assistant_message=build_conversation_message_read(assistant_message),
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
