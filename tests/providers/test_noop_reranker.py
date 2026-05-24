from __future__ import annotations

import pytest

from app.providers.reranker import (
    NoopRerankerProvider,
    RerankCandidate,
    get_reranker_provider,
)
from app.core.config import get_settings


@pytest.mark.anyio
async def test_noop_reranker_preserves_order_and_top_n() -> None:
    provider = NoopRerankerProvider()
    results = await provider.rerank(
        query="deployment",
        candidates=[
            RerankCandidate(id="a", text="first"),
            RerankCandidate(id="b", text="second"),
            RerankCandidate(id="c", text="third"),
        ],
        top_n=2,
    )

    assert [item.id for item in results] == ["a", "b"]
    assert [item.rank for item in results] == [1, 2]
    assert all(item.score == 0.0 for item in results)


@pytest.mark.anyio
async def test_noop_reranker_info_reports_disabled() -> None:
    provider = NoopRerankerProvider()
    info = await provider.get_info()

    assert info.provider == "noop"
    assert info.enabled is False
    assert info.available is True


@pytest.mark.anyio
async def test_noop_reranker_handles_empty_candidates() -> None:
    provider = NoopRerankerProvider()

    assert await provider.rerank(query="anything", candidates=[], top_n=5) == []


def test_reranker_factory_returns_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setenv("RERANKER_PROVIDER", "noop")
    get_settings.cache_clear()

    provider = get_reranker_provider()

    assert isinstance(provider, NoopRerankerProvider)
    get_settings.cache_clear()
