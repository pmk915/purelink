from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, Field


class RerankerProviderError(ValueError):
    pass


class RerankCandidate(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankResult(BaseModel):
    id: str
    score: float
    rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankerProviderInfo(BaseModel):
    provider: str
    model_name: str | None = None
    enabled: bool = False
    available: bool = True
    error: str | None = None


class RerankerProvider(Protocol):
    provider_name: str
    model_name: str | None

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_n: int,
    ) -> list[RerankResult]: ...

    async def get_info(self) -> RerankerProviderInfo: ...
