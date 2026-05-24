from __future__ import annotations

from app.providers.llm.base import (
    LLMCompletionRequest,
    LLMCompletionResult,
    LLMProviderInfo,
)
from app.schemas.llm import HEURISTIC_PROVIDER
from app.services.llm import generate_openai_compatible_chat_completion


class HeuristicLLMProvider:
    provider_name = HEURISTIC_PROVIDER
    model_name = None

    async def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        user_content = "\n".join(
            item.content for item in request.messages if item.role == "user"
        ).strip()
        return LLMCompletionResult(
            content=user_content or "OK",
            model_name=self.model_name,
        )

    async def get_info(self) -> LLMProviderInfo:
        return LLMProviderInfo(provider=self.provider_name, model_name=self.model_name)


class OpenAICompatibleLegacyLLMProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        api_base: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        reasoning_effort: str | None = None,
        thinking_enabled: bool = False,
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.api_base = api_base
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.thinking_enabled = thinking_enabled

    async def complete(self, request: LLMCompletionRequest) -> LLMCompletionResult:
        system_prompt = "\n".join(
            item.content for item in request.messages if item.role == "system"
        )
        user_prompt = "\n".join(
            item.content for item in request.messages if item.role != "system"
        )
        content = generate_openai_compatible_chat_completion(
            api_base=self.api_base,
            api_key=self.api_key,
            model=self.model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout=self.timeout_seconds,
            reasoning_effort=self.reasoning_effort,
            thinking_enabled=self.thinking_enabled,
        )
        return LLMCompletionResult(content=content, model_name=self.model_name)

    async def get_info(self) -> LLMProviderInfo:
        return LLMProviderInfo(provider=self.provider_name, model_name=self.model_name)
