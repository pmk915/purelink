from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.fastembed_provider import FastEmbedEmbeddingProvider
from app.providers.embedding.legacy_adapter import LegacyEmbeddingProviderAdapter
from app.services.embedding_provider import (
    DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE,
    DEFAULT_EXTERNAL_EMBEDDING_TIMEOUT_SECONDS,
    DEFAULT_FASTEMBED_MODEL,
    DEFAULT_SENTENCE_TRANSFORMERS_DEVICE,
    FASTEMBED_PROVIDER,
    EmbeddingProviderError,
    resolve_embedding_provider,
)


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    active_settings = settings or get_settings()
    return _get_embedding_provider_cached(
        provider=active_settings.embedding_provider,
        api_base=active_settings.embedding_api_base,
        api_key=active_settings.embedding_api_key,
        model=active_settings.embedding_model,
        device=active_settings.embedding_device,
        normalize=active_settings.embedding_normalize,
        cache_dir=active_settings.embedding_model_cache_dir,
        timeout_seconds=active_settings.embedding_timeout_seconds,
        batch_size=active_settings.embedding_batch_size,
        dimension=active_settings.embedding_dimension,
    )


@lru_cache(maxsize=8)
def _get_embedding_provider_cached(
    *,
    provider: str,
    api_base: str,
    api_key: str,
    model: str,
    device: str,
    normalize: bool,
    cache_dir: str,
    timeout_seconds: float,
    batch_size: int,
    dimension: int | None,
) -> EmbeddingProvider:
    normalized_provider = (provider or FASTEMBED_PROVIDER).strip().lower()
    if normalized_provider == FASTEMBED_PROVIDER:
        return FastEmbedEmbeddingProvider(
            model_name=model.strip() or DEFAULT_FASTEMBED_MODEL,
            cache_dir=cache_dir,
            normalize=normalize,
            batch_size=batch_size,
        )

    legacy_provider = resolve_embedding_provider(
        normalized_provider,
        api_base=api_base,
        api_key=api_key,
        model=model,
        device=device or DEFAULT_SENTENCE_TRANSFORMERS_DEVICE,
        normalize=normalize,
        cache_dir=cache_dir,
        timeout_seconds=timeout_seconds or DEFAULT_EXTERNAL_EMBEDDING_TIMEOUT_SECONDS,
        batch_size=batch_size or DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE,
        dimension=dimension,
    )
    return LegacyEmbeddingProviderAdapter(legacy_provider)


def reset_embedding_provider_cache() -> None:
    _get_embedding_provider_cached.cache_clear()


__all__ = [
    "EmbeddingProviderError",
    "get_embedding_provider",
    "reset_embedding_provider_cache",
]
