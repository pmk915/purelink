from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMCompletionRequest(BaseModel):
    messages: list[LLMMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMCompletionResult(BaseModel):
    content: str
    model_name: str | None = None
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


class LLMProviderInfo(BaseModel):
    provider: str
    model_name: str | None = None
    available: bool = True
    error: str | None = None


class LLMProvider(Protocol):
    provider_name: str
    model_name: str | None

    async def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult: ...

    async def get_info(self) -> LLMProviderInfo: ...
