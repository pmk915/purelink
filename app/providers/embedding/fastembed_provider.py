from __future__ import annotations

from collections.abc import Sequence

from app.providers.embedding.base import EmbeddingProviderInfo
from app.services.embedding_provider import (
    DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE,
    DEFAULT_FASTEMBED_MODEL,
    FASTEMBED_PROVIDER,
    FastEmbedEmbeddingProvider as LegacyFastEmbedEmbeddingProvider,
)


class FastEmbedEmbeddingProvider:
    provider_name = FASTEMBED_PROVIDER

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_FASTEMBED_MODEL,
        cache_dir: str | None = None,
        normalize: bool = True,
        batch_size: int = DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE,
    ) -> None:
        self.model_name = model_name or DEFAULT_FASTEMBED_MODEL
        self._legacy_provider = LegacyFastEmbedEmbeddingProvider(
            model=self.model_name,
            normalize=normalize,
            cache_dir=cache_dir or "",
            max_batch_size=batch_size,
        )

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return self._legacy_provider.embed_texts(list(texts))

    async def embed_query(self, query: str) -> list[float]:
        return self._legacy_provider.embed_query(query)

    async def get_info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            dim=self._legacy_provider.default_dimension or None,
            normalize=self._legacy_provider.normalize,
            available=True,
        )
