from __future__ import annotations

from app.core.config import Settings, get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.legacy_adapter import (
    HeuristicLLMProvider,
    OpenAICompatibleLegacyLLMProvider,
)
from app.schemas.llm import (
    DEEPSEEK_PROVIDER,
    HEURISTIC_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
)


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    active_settings = settings or get_settings()
    provider = active_settings.llm_provider.strip().lower()
    if provider == HEURISTIC_PROVIDER:
        return HeuristicLLMProvider()
    if provider in {OPENAI_COMPATIBLE_PROVIDER, DEEPSEEK_PROVIDER}:
        return OpenAICompatibleLegacyLLMProvider(
            provider_name=provider,
            api_base=active_settings.llm_api_base,
            api_key=active_settings.llm_api_key,
            model_name=active_settings.llm_model,
            timeout_seconds=active_settings.llm_timeout_seconds,
            reasoning_effort=(
                active_settings.llm_reasoning_effort
                if provider == DEEPSEEK_PROVIDER
                else None
            ),
            thinking_enabled=(
                active_settings.llm_thinking_enabled
                if provider == DEEPSEEK_PROVIDER
                else False
            ),
        )
    raise NotImplementedError(f"Unsupported LLM provider: {provider}.")
