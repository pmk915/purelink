from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.providers.reranker.base import (
    RerankCandidate,
    RerankResult,
    RerankerProviderError,
    RerankerProviderInfo,
)


FLAGEMBEDDING_RERANKER_PROVIDER = "flagembedding"
DEFAULT_FLAGEMBEDDING_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
MISSING_FLAGEMBEDDING_ERROR = (
    "FlagEmbedding is required for RERANKER_PROVIDER=flagembedding. "
    "Install the optional reranker dependencies or disable reranker."
)


class FlagEmbeddingRerankerProvider:
    provider_name = FLAGEMBEDDING_RERANKER_PROVIDER

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_FLAGEMBEDDING_RERANKER_MODEL,
        use_fp16: bool = True,
    ) -> None:
        self.model_name = model_name or DEFAULT_FLAGEMBEDDING_RERANKER_MODEL
        self.use_fp16 = use_fp16

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_n: int,
    ) -> list[RerankResult]:
        if top_n <= 0 or not candidates:
            return []

        reranker = _load_flagembedding_reranker(
            model_name=self.model_name,
            use_fp16=self.use_fp16,
        )
        pairs = [[query, candidate.text] for candidate in candidates]
        try:
            raw_scores = reranker.compute_score(pairs)
        except Exception as exc:  # pragma: no cover - provider-specific runtime guard
            raise RerankerProviderError(
                f"FlagEmbedding rerank failed for model '{self.model_name}'."
            ) from exc

        if isinstance(raw_scores, (int, float)):
            scores = [float(raw_scores)]
        else:
            scores = [float(item) for item in raw_scores]
        scored = [
            (scores[index] if index < len(scores) else 0.0, index, candidate)
            for index, candidate in enumerate(candidates)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))

        return [
            RerankResult(
                id=candidate.id,
                score=score,
                rank=rank,
                metadata=candidate.metadata,
            )
            for rank, (score, _, candidate) in enumerate(scored[:top_n], start=1)
        ]

    async def get_info(self) -> RerankerProviderInfo:
        error = probe_flagembedding_error()
        return RerankerProviderInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            enabled=True,
            available=error is None,
            error=error,
        )


def probe_flagembedding_error() -> str | None:
    try:
        _import_flag_reranker_class()
    except RerankerProviderError as exc:
        return str(exc)
    return None


@lru_cache(maxsize=2)
def _load_flagembedding_reranker(*, model_name: str, use_fp16: bool):
    FlagReranker = _import_flag_reranker_class()
    try:
        return FlagReranker(model_name, use_fp16=use_fp16)
    except Exception as exc:  # pragma: no cover - provider-specific runtime guard
        raise RerankerProviderError(
            f"Failed to load FlagEmbedding reranker model '{model_name}'."
        ) from exc


def _import_flag_reranker_class():
    try:
        from FlagEmbedding import FlagReranker
    except ImportError as exc:
        raise RerankerProviderError(MISSING_FLAGEMBEDDING_ERROR) from exc
    return FlagReranker
