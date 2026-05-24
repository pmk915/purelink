from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.providers.embedding import get_embedding_provider, reset_embedding_provider_cache
from app.services.embedding_provider import EmbeddingProviderError


@pytest.mark.anyio
async def test_default_embedding_provider_reports_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    get_settings.cache_clear()
    reset_embedding_provider_cache()

    provider = get_embedding_provider()
    info = await provider.get_info()

    assert info.provider == "fastembed"
    assert info.model_name == "BAAI/bge-small-zh-v1.5"
    assert info.available is True

    get_settings.cache_clear()
    reset_embedding_provider_cache()


@pytest.mark.anyio
async def test_configured_embedding_provider_name_is_respected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hashed_bow")
    get_settings.cache_clear()
    reset_embedding_provider_cache()

    provider = get_embedding_provider()
    info = await provider.get_info()

    assert info.provider == "local_hashed_bow"
    assert info.model_name == "hashed_bow_v1"
    assert info.dim == 128

    get_settings.cache_clear()
    reset_embedding_provider_cache()


def test_unsupported_embedding_provider_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "unknown_embedding")
    get_settings.cache_clear()
    reset_embedding_provider_cache()

    with pytest.raises(EmbeddingProviderError, match="Unsupported embedding provider"):
        get_embedding_provider()

    get_settings.cache_clear()
    reset_embedding_provider_cache()
