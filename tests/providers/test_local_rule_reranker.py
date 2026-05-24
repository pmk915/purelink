from __future__ import annotations

import pytest

from app.providers.reranker import RerankCandidate
from app.providers.reranker.local_rule_reranker import LocalRuleRerankerProvider


@pytest.mark.anyio
async def test_local_rule_reranker_promotes_exact_term_match() -> None:
    provider = LocalRuleRerankerProvider()

    results = await provider.rerank(
        query="alpha deployment checklist",
        candidates=[
            RerankCandidate(id="general", text="General project overview."),
            RerankCandidate(
                id="match",
                text="Alpha deployment checklist includes rollback steps.",
            ),
        ],
        top_n=2,
    )

    assert [item.id for item in results] == ["match", "general"]
    assert results[0].score > results[1].score


@pytest.mark.anyio
async def test_local_rule_reranker_preserves_stable_order_for_ties() -> None:
    provider = LocalRuleRerankerProvider()

    results = await provider.rerank(
        query="missing",
        candidates=[
            RerankCandidate(id="a", text="first"),
            RerankCandidate(id="b", text="second"),
        ],
        top_n=2,
    )

    assert [item.id for item in results] == ["a", "b"]


@pytest.mark.anyio
async def test_local_rule_reranker_respects_top_n_and_empty_inputs() -> None:
    provider = LocalRuleRerankerProvider()

    results = await provider.rerank(
        query="alpha",
        candidates=[
            RerankCandidate(id="a", text="alpha"),
            RerankCandidate(id="b", text="alpha beta"),
        ],
        top_n=1,
    )

    assert len(results) == 1
    assert await provider.rerank(query="alpha", candidates=[], top_n=5) == []


@pytest.mark.anyio
async def test_local_rule_reranker_handles_empty_query() -> None:
    provider = LocalRuleRerankerProvider()

    results = await provider.rerank(
        query=" ",
        candidates=[RerankCandidate(id="a", text="alpha")],
        top_n=1,
    )

    assert results[0].id == "a"
    assert results[0].score == 0.0
