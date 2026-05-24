from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.providers.reranker import (
    FlagEmbeddingRerankerProvider,
    LocalRuleRerankerProvider,
    NoopRerankerProvider,
    RerankerProviderError,
    get_reranker_provider,
)


def test_reranker_factory_returns_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setenv("RERANKER_PROVIDER", "local_rule_reranker")
    get_settings.cache_clear()

    assert isinstance(get_reranker_provider(), NoopRerankerProvider)

    get_settings.cache_clear()


def test_reranker_factory_returns_local_rule_provider_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "local_rule_reranker")
    get_settings.cache_clear()

    assert isinstance(get_reranker_provider(), LocalRuleRerankerProvider)

    get_settings.cache_clear()


def test_reranker_factory_returns_flagembedding_provider_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "flagembedding")
    monkeypatch.setenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    get_settings.cache_clear()

    provider = get_reranker_provider()

    assert isinstance(provider, FlagEmbeddingRerankerProvider)
    assert provider.model_name == "BAAI/bge-reranker-v2-m3"

    get_settings.cache_clear()


def test_reranker_factory_unsupported_provider_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "unknown_reranker")
    get_settings.cache_clear()

    with pytest.raises(RerankerProviderError, match="Unknown reranker provider"):
        get_reranker_provider()

    get_settings.cache_clear()
