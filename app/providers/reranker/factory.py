from __future__ import annotations

from app.core.config import Settings, get_settings
from app.providers.reranker.base import RerankerProvider, RerankerProviderError
from app.providers.reranker.flagembedding_reranker import (
    FLAGEMBEDDING_RERANKER_PROVIDER,
    FlagEmbeddingRerankerProvider,
)
from app.providers.reranker.local_rule_reranker import LocalRuleRerankerProvider
from app.providers.reranker.noop_reranker import (
    NOOP_RERANKER_PROVIDER,
    NoopRerankerProvider,
)
from app.services.reranking import (
    CROSS_ENCODER_RERANKER,
    EXTERNAL_RERANK_API,
    LLM_RERANKER,
    LOCAL_RULE_RERANKER,
)


def get_reranker_provider(settings: Settings | None = None) -> RerankerProvider:
    active_settings = settings or get_settings()
    if not active_settings.reranker_enabled:
        return NoopRerankerProvider()

    provider = (active_settings.reranker_provider or NOOP_RERANKER_PROVIDER).strip().lower()
    if provider == NOOP_RERANKER_PROVIDER:
        return NoopRerankerProvider()
    if provider == LOCAL_RULE_RERANKER:
        return LocalRuleRerankerProvider()
    if provider == FLAGEMBEDDING_RERANKER_PROVIDER:
        return FlagEmbeddingRerankerProvider(
            model_name=active_settings.reranker_model,
        )
    if provider in {EXTERNAL_RERANK_API, CROSS_ENCODER_RERANKER, LLM_RERANKER}:
        raise RerankerProviderError(f"Reranker provider is not implemented in M3: {provider}.")
    raise RerankerProviderError(f"Unknown reranker provider: {provider}.")
