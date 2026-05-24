from __future__ import annotations

from collections.abc import Sequence

from app.providers.reranker.base import (
    RerankCandidate,
    RerankResult,
    RerankerProviderInfo,
)


NOOP_RERANKER_PROVIDER = "noop"


class NoopRerankerProvider:
    provider_name = NOOP_RERANKER_PROVIDER
    model_name = None

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_n: int,
    ) -> list[RerankResult]:
        if top_n <= 0:
            return []
        return [
            RerankResult(
                id=candidate.id,
                score=0.0,
                rank=index + 1,
                metadata=candidate.metadata,
            )
            for index, candidate in enumerate(candidates[:top_n])
        ]

    async def get_info(self) -> RerankerProviderInfo:
        return RerankerProviderInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            enabled=False,
            available=True,
        )
