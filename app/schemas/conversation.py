from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

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
