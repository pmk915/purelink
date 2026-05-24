from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel


class EmbeddingProviderInfo(BaseModel):
    provider: str
    model_name: str
    dim: int | None = None
    max_tokens: int | None = None
    normalize: bool | None = None
    available: bool = True
    error: str | None = None


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...

    async def get_info(self) -> EmbeddingProviderInfo: ...
