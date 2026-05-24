from __future__ import annotations

import pytest

from app.providers.reranker import RerankCandidate, RerankerProviderError
from app.providers.reranker.flagembedding_reranker import (
    FlagEmbeddingRerankerProvider,
    MISSING_FLAGEMBEDDING_ERROR,
)


@pytest.mark.anyio
async def test_flagembedding_missing_dependency_reports_clear_error() -> None:
    provider = FlagEmbeddingRerankerProvider()
    info = await provider.get_info()

    if info.available:
        pytest.skip("FlagEmbedding is installed in this environment.")

    assert info.error == MISSING_FLAGEMBEDDING_ERROR
    with pytest.raises(RerankerProviderError, match="FlagEmbedding is required"):
        await provider.rerank(
            query="alpha",
            candidates=[RerankCandidate(id="a", text="alpha text")],
            top_n=1,
        )
