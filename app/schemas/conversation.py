from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import MessageRole
from app.schemas.qa import CitationRead


class ConversationSummaryRead(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    scope: str
    team_id: int | None
    created_at: datetime
    updated_at: datetime


class ConversationMessageRead(BaseModel):
    id: int
    role: MessageRole
    content: str
    citations: list[CitationRead]
    created_at: datetime


class ConversationRead(ConversationSummaryRead):
    messages: list[ConversationMessageRead]


class ConversationMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message content cannot be empty.")
        return normalized


class AppendConversationMessageResponse(BaseModel):
    conversation: ConversationSummaryRead
    user_message: ConversationMessageRead
    assistant_message: ConversationMessageRead
