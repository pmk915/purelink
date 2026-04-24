from __future__ import annotations

import httpx
import pytest

from app.services.embedding_provider import (
    HASHED_BOW_SCHEME,
    OPENAI_COMPATIBLE_EMBEDDING_SCHEME,
    EmbeddingProviderError,
    OpenAICompatibleEmbeddingProvider,
    resolve_embedding_provider,
)


def test_local_hashed_bow_provider_embeds_text_and_query() -> None:
    provider = resolve_embedding_provider("local_hashed_bow")

    text_vector = provider.embed_text("PureLink local fallback embedding", dimension=16)
    query_vector = provider.embed_query("PureLink local fallback embedding", dimension=16)
    batch_vectors = provider.embed_texts(
        ["PureLink local fallback embedding", "Second chunk"],
        dimension=16,
    )

    assert provider.scheme == HASHED_BOW_SCHEME
    assert provider.provider_name == "local_hashed_bow"
    assert len(text_vector) == 16
    assert text_vector == query_vector
    assert len(batch_vectors) == 2
    assert all(len(item) == 16 for item in batch_vectors)


def test_openai_compatible_embedding_provider_batches_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {"index": 0, "embedding": [3.0, 4.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 0.0, 2.0]},
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    monkeypatch.setattr("app.services.embedding_provider.httpx.post", fake_post)

    provider = OpenAICompatibleEmbeddingProvider(
        api_base="https://embedding.example/v1",
        api_key="test-key",
        model="semantic-model",
        timeout_seconds=7.5,
        max_batch_size=8,
        default_dimension=3,
    )

    vectors = provider.embed_texts(["first", "second"], dimension=3)

    assert provider.scheme == OPENAI_COMPATIBLE_EMBEDDING_SCHEME
    assert provider.provider_name == "openai_compatible"
    assert provider.version == "semantic-model"
    assert calls[0]["url"] == "https://embedding.example/v1/embeddings"
    assert calls[0]["json"] == {
        "model": "semantic-model",
        "input": ["first", "second"],
        "dimensions": 3,
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["timeout"] == 7.5
    assert vectors == [
        [0.6, 0.8, 0.0],
        [0.0, 0.0, 1.0],
    ]


def test_openai_compatible_embedding_provider_reports_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr("app.services.embedding_provider.httpx.post", fake_post)
    provider = OpenAICompatibleEmbeddingProvider(
        api_base="https://embedding.example/v1",
        api_key="test-key",
        model="semantic-model",
    )

    with pytest.raises(EmbeddingProviderError, match="Embedding request failed"):
        provider.embed_query("PureLink")
