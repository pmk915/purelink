from __future__ import annotations

import httpx
import pytest

from app.services.embedding_provider import (
    FASTEMBED_SCHEME,
    HASHED_BOW_SCHEME,
    OPENAI_COMPATIBLE_EMBEDDING_SCHEME,
    SENTENCE_TRANSFORMERS_SCHEME,
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


def test_fastembed_provider_embeds_fixed_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_texts: list[str] = []

    class FakeFastEmbedModel:
        def embed(self, texts, *, batch_size):
            assert batch_size == 8
            captured_texts.extend(texts)
            return [
                [1.0, 0.0, 0.0, float(index + 1)]
                for index, _ in enumerate(texts)
            ]

    monkeypatch.setattr(
        "app.services.embedding_provider._load_fastembed_model",
        lambda **kwargs: FakeFastEmbedModel(),
    )

    provider = resolve_embedding_provider(
        "fastembed",
        model="BAAI/bge-small-zh-v1.5",
        normalize=True,
        cache_dir="/tmp/embedding-cache",
        batch_size=8,
    )
    vectors = provider.embed_texts(["first", "second"])
    query_vector = provider.embed_query("question")

    assert provider.scheme == FASTEMBED_SCHEME
    assert provider.provider_name == "fastembed"
    assert provider.version == "BAAI/bge-small-zh-v1.5"
    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)
    assert len(query_vector) == 4
    assert captured_texts[:2] == ["passage: first", "passage: second"]
    assert captured_texts[2] == "query: question"


def test_sentence_transformers_provider_embeds_fixed_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSentenceTransformer:
        def __init__(self, *, model_name_or_path, device=None, cache_folder=None) -> None:
            self.model_name_or_path = model_name_or_path
            self.device = device
            self.cache_folder = cache_folder

        def encode(
            self,
            texts,
            *,
            batch_size,
            show_progress_bar,
            normalize_embeddings,
            convert_to_numpy,
        ):
            assert batch_size == 8
            assert show_progress_bar is False
            assert normalize_embeddings is True
            assert convert_to_numpy is True
            return [
                [1.0, 0.0, 0.0, float(index + 1)]
                for index, _ in enumerate(texts)
            ]

    monkeypatch.setattr(
        "app.services.embedding_provider._load_sentence_transformer_model",
        lambda **kwargs: FakeSentenceTransformer(
            model_name_or_path=kwargs["model_name"],
            device=kwargs.get("device"),
            cache_folder=kwargs.get("cache_dir"),
        ),
    )

    provider = resolve_embedding_provider(
        "sentence_transformers",
        model="BAAI/bge-small-zh-v1.5",
        device="cpu",
        normalize=True,
        cache_dir="/tmp/embedding-cache",
        batch_size=8,
    )
    vectors = provider.embed_texts(["first", "second"])

    assert provider.scheme == SENTENCE_TRANSFORMERS_SCHEME
    assert provider.provider_name == "sentence_transformers"
    assert provider.version == "BAAI/bge-small-zh-v1.5"
    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)


def test_sentence_transformers_provider_reports_load_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_load(**kwargs):
        raise EmbeddingProviderError("Failed to load sentence_transformers model 'broken-model'.")

    monkeypatch.setattr(
        "app.services.embedding_provider._load_sentence_transformer_model",
        fail_load,
    )

    provider = resolve_embedding_provider(
        "sentence_transformers",
        model="broken-model",
    )

    with pytest.raises(EmbeddingProviderError, match="Failed to load sentence_transformers model"):
        provider.embed_query("PureLink")


def test_sentence_transformers_provider_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = resolve_embedding_provider(
        "sentence_transformers",
        model="BAAI/bge-small-zh-v1.5",
    )

    def fail_import(name: str):
        if name == "sentence_transformers":
            raise ModuleNotFoundError("sentence_transformers")
        raise AssertionError(name)

    monkeypatch.setattr("app.services.embedding_provider.importlib.import_module", fail_import)

    with pytest.raises(EmbeddingProviderError) as exc_info:
        provider.embed_query("PureLink")

    assert exc_info.value.error_code == "EMBEDDING_PROVIDER_NOT_INSTALLED"
