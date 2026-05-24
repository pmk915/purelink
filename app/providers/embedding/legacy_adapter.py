from __future__ import annotations

from collections.abc import Sequence

from app.providers.embedding.base import EmbeddingProviderInfo
from app.services.embedding_provider import EmbeddingProvider as LegacyEmbeddingProvider


class LegacyEmbeddingProviderAdapter:
    def __init__(self, provider: LegacyEmbeddingProvider) -> None:
        self.provider = provider
        self.provider_name = provider.provider_name
        self.model_name = provider.model

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return self.provider.embed_texts(list(texts))

    async def embed_query(self, query: str) -> list[float]:
        return self.provider.embed_query(query)

    async def get_info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            dim=self.provider.default_dimension or None,
            normalize=self.provider.normalize,
            available=True,
        )
