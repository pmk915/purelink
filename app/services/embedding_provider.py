from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib
from functools import lru_cache
import math
import re
from typing import Protocol

import httpx


DEFAULT_EMBEDDING_DIMENSION = 128
HASHED_BOW_SCHEME = "hashed_bow_v1"
LOCAL_HASHED_BOW_PROVIDER = "local_hashed_bow"
FASTEMBED_PROVIDER = "fastembed"
FASTEMBED_SCHEME = "fastembed_v1"
SENTENCE_TRANSFORMERS_PROVIDER = "sentence_transformers"
SENTENCE_TRANSFORMERS_SCHEME = "sentence_transformers_v1"
OPENAI_COMPATIBLE_EMBEDDING_PROVIDER = "openai_compatible"
OPENAI_COMPATIBLE_EMBEDDING_SCHEME = "openai_compatible_embedding_v1"
DEFAULT_EXTERNAL_EMBEDDING_TIMEOUT_SECONDS = 30.0
DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE = 32
DEFAULT_SENTENCE_TRANSFORMERS_DEVICE = "cpu"
DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-zh-v1.5"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


class EmbeddingProviderError(ValueError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class EmbeddingProvider(Protocol):
    scheme: str
    provider_name: str
    model: str
    version: str
    default_dimension: int
    max_batch_size: int
    normalize: bool

    def embed_text(self, text: str, *, dimension: int | None = None) -> list[float]: ...

    def embed_texts(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]: ...

    def embed_query(self, text: str, *, dimension: int | None = None) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class LocalHashedBowEmbeddingProvider:
    scheme: str = HASHED_BOW_SCHEME
    provider_name: str = LOCAL_HASHED_BOW_PROVIDER
    model: str = HASHED_BOW_SCHEME
    version: str = HASHED_BOW_SCHEME
    default_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    max_batch_size: int = 256
    normalize: bool = True

    def embed_text(self, text: str, *, dimension: int | None = None) -> list[float]:
        active_dimension = dimension or self.default_dimension
        if active_dimension <= 0:
            raise EmbeddingProviderError("Embedding dimension must be greater than zero.")

        tokens = tokenize_text(text)
        if not tokens:
            raise EmbeddingProviderError("Text contains no tokens for embedding.")

        vector = [0.0] * active_dimension
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % active_dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            raise EmbeddingProviderError("Text embedding could not be normalized.")
        return [value / magnitude for value in vector]

    def embed_texts(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        return [self.embed_text(text, dimension=dimension) for text in texts]

    def embed_query(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self.embed_text(text, dimension=dimension)


@dataclass(frozen=True, slots=True)
class FastEmbedEmbeddingProvider:
    model: str = DEFAULT_FASTEMBED_MODEL
    normalize: bool = True
    cache_dir: str = ""
    max_batch_size: int = DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE
    scheme: str = FASTEMBED_SCHEME
    provider_name: str = FASTEMBED_PROVIDER
    default_dimension: int = 0

    @property
    def version(self) -> str:
        return self.model

    def embed_text(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self.embed_texts([_prepare_fastembed_passage(text)], dimension=dimension)[0]

    def embed_query(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self._embed_prepared_texts([_prepare_fastembed_query(text)], dimension=dimension)[0]

    def embed_texts(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        prepared_texts = [_prepare_fastembed_passage(text) for text in texts]
        return self._embed_prepared_texts(prepared_texts, dimension=dimension)

    def _embed_prepared_texts(
        self,
        texts: list[str],
        *,
        dimension: int | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        if self.max_batch_size <= 0:
            raise EmbeddingProviderError("Embedding batch size must be greater than zero.")
        model = _load_fastembed_model(
            model_name=self.model or DEFAULT_FASTEMBED_MODEL,
            cache_dir=self.cache_dir,
        )
        try:
            encoded = list(model.embed(texts, batch_size=self.max_batch_size))
        except Exception as exc:  # pragma: no cover - provider-specific runtime guard
            raise EmbeddingProviderError(
                f"Failed to encode text with fastembed model '{self.model or DEFAULT_FASTEMBED_MODEL}'."
            ) from exc

        vectors = _coerce_fastembed_vectors(encoded)
        if dimension is not None and dimension > 0:
            actual_dimension = len(vectors[0]) if vectors else 0
            if actual_dimension != dimension:
                raise EmbeddingProviderError(
                    "Configured embedding dimension does not match fastembed output dimension."
                )
        if not self.normalize:
            return vectors
        return [_normalize_vector(vector) for vector in vectors]


@dataclass(frozen=True, slots=True)
class OpenAICompatibleEmbeddingProvider:
    api_base: str
    api_key: str
    model: str
    timeout_seconds: float = DEFAULT_EXTERNAL_EMBEDDING_TIMEOUT_SECONDS
    max_batch_size: int = DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE
    scheme: str = OPENAI_COMPATIBLE_EMBEDDING_SCHEME
    provider_name: str = OPENAI_COMPATIBLE_EMBEDDING_PROVIDER
    default_dimension: int = 0
    normalize: bool = True

    @property
    def version(self) -> str:
        return self.model

    def embed_text(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self.embed_texts([text], dimension=dimension)[0]

    def embed_query(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self.embed_text(text, dimension=dimension)

    def embed_texts(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_base:
            raise EmbeddingProviderError(
                "EMBEDDING_API_BASE_URL is required for external embedding provider."
            )
        if not self.api_key:
            raise EmbeddingProviderError("EMBEDDING_API_KEY is required for external embedding provider.")
        if not self.model:
            raise EmbeddingProviderError("EMBEDDING_MODEL is required for external embedding provider.")
        if self.max_batch_size <= 0:
            raise EmbeddingProviderError("Embedding batch size must be greater than zero.")

        vectors: list[list[float]] = []
        for start_index in range(0, len(texts), self.max_batch_size):
            batch = texts[start_index : start_index + self.max_batch_size]
            vectors.extend(self._embed_batch(batch, dimension=dimension))
        return vectors

    def _embed_batch(self, texts: list[str], *, dimension: int | None) -> list[list[float]]:
        endpoint = f"{self.api_base.rstrip('/')}/embeddings"
        payload: dict[str, object] = {
            "model": self.model,
            "input": texts,
        }
        if dimension is not None and dimension > 0:
            payload["dimensions"] = dimension

        try:
            response = httpx.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError(
                "Embedding request timed out. Check EMBEDDING_API_BASE_URL, network access, and EMBEDDING_TIMEOUT_SECONDS."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingProviderError(
                f"Embedding provider returned HTTP {exc.response.status_code}. Check EMBEDDING_API_KEY and EMBEDDING_MODEL."
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(
                "Embedding request failed. Check EMBEDDING_API_BASE_URL and provider network access."
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("Embedding response is not valid JSON.") from exc

        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingProviderError("Embedding response does not match input batch.")

        ordered_items = sorted(
            enumerate(data),
            key=lambda indexed: _coerce_embedding_index(indexed[1], fallback=indexed[0]),
        )
        vectors: list[list[float]] = []
        for _, item in ordered_items:
            if not isinstance(item, dict):
                raise EmbeddingProviderError("Embedding response item is invalid.")
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingProviderError("Embedding response item is missing vector data.")
            vector = _coerce_embedding_vector(embedding)
            vectors.append(_normalize_vector(vector))
        return vectors


@dataclass(frozen=True, slots=True)
class SentenceTransformersEmbeddingProvider:
    model: str
    device: str = DEFAULT_SENTENCE_TRANSFORMERS_DEVICE
    normalize: bool = True
    cache_dir: str = ""
    max_batch_size: int = DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE
    scheme: str = SENTENCE_TRANSFORMERS_SCHEME
    provider_name: str = SENTENCE_TRANSFORMERS_PROVIDER
    default_dimension: int = 0

    @property
    def version(self) -> str:
        return self.model

    def embed_text(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self.embed_texts([text], dimension=dimension)[0]

    def embed_query(self, text: str, *, dimension: int | None = None) -> list[float]:
        return self.embed_text(text, dimension=dimension)

    def embed_texts(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        if not texts:
            return []
        if not self.model:
            raise EmbeddingProviderError(
                "EMBEDDING_MODEL is required for sentence_transformers provider."
            )
        if self.max_batch_size <= 0:
            raise EmbeddingProviderError("Embedding batch size must be greater than zero.")

        model = _load_sentence_transformer_model(
            model_name=self.model,
            device=self.device,
            cache_dir=self.cache_dir,
        )
        try:
            encoded = model.encode(
                texts,
                batch_size=self.max_batch_size,
                show_progress_bar=False,
                normalize_embeddings=self.normalize,
                convert_to_numpy=True,
            )
        except Exception as exc:  # pragma: no cover - provider-specific runtime guard
            raise EmbeddingProviderError(
                f"Failed to encode text with sentence_transformers model '{self.model}'."
            ) from exc

        vectors = _coerce_sentence_transformer_vectors(encoded)
        if dimension is not None and dimension > 0:
            actual_dimension = len(vectors[0]) if vectors else 0
            if actual_dimension != dimension:
                raise EmbeddingProviderError(
                    "Configured embedding dimension does not match sentence_transformers output dimension."
                )
        if not self.normalize:
            return vectors
        return [_normalize_vector(vector) for vector in vectors]


DEFAULT_EMBEDDING_PROVIDER = LocalHashedBowEmbeddingProvider()


def resolve_embedding_provider(
    scheme: str | None = None,
    *,
    api_base: str = "",
    api_key: str = "",
    model: str = "",
    device: str = DEFAULT_SENTENCE_TRANSFORMERS_DEVICE,
    normalize: bool = True,
    cache_dir: str = "",
    timeout_seconds: float = DEFAULT_EXTERNAL_EMBEDDING_TIMEOUT_SECONDS,
    batch_size: int = DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE,
    dimension: int | None = None,
) -> EmbeddingProvider:
    normalized_scheme = (scheme or FASTEMBED_PROVIDER).strip().lower()
    if normalized_scheme in {LOCAL_HASHED_BOW_PROVIDER, HASHED_BOW_SCHEME}:
        return DEFAULT_EMBEDDING_PROVIDER
    if normalized_scheme in {FASTEMBED_PROVIDER, FASTEMBED_SCHEME}:
        return FastEmbedEmbeddingProvider(
            model=model.strip() or DEFAULT_FASTEMBED_MODEL,
            normalize=normalize,
            cache_dir=cache_dir.strip(),
            max_batch_size=batch_size,
        )
    if normalized_scheme in {
        SENTENCE_TRANSFORMERS_PROVIDER,
        SENTENCE_TRANSFORMERS_SCHEME,
    }:
        return SentenceTransformersEmbeddingProvider(
            model=model.strip(),
            device=(device or DEFAULT_SENTENCE_TRANSFORMERS_DEVICE).strip().lower(),
            normalize=normalize,
            cache_dir=cache_dir.strip(),
            max_batch_size=batch_size,
        )
    if normalized_scheme in {
        OPENAI_COMPATIBLE_EMBEDDING_PROVIDER,
        OPENAI_COMPATIBLE_EMBEDDING_SCHEME,
        "external_embedding_api",
    }:
        return OpenAICompatibleEmbeddingProvider(
            api_base=api_base.strip(),
            api_key=api_key.strip(),
            model=model.strip(),
            timeout_seconds=timeout_seconds,
            max_batch_size=batch_size,
            default_dimension=dimension or 0,
        )
    raise EmbeddingProviderError(f"Unsupported embedding provider scheme: {normalized_scheme}.")


def resolve_configured_embedding_provider(settings: object) -> EmbeddingProvider:
    return resolve_embedding_provider(
        getattr(settings, "embedding_provider", FASTEMBED_PROVIDER),
        api_base=getattr(settings, "embedding_api_base", ""),
        api_key=getattr(settings, "embedding_api_key", ""),
        model=getattr(settings, "embedding_model", ""),
        device=getattr(settings, "embedding_device", DEFAULT_SENTENCE_TRANSFORMERS_DEVICE),
        normalize=bool(getattr(settings, "embedding_normalize", True)),
        cache_dir=getattr(settings, "embedding_model_cache_dir", ""),
        timeout_seconds=float(
            getattr(
                settings,
                "embedding_timeout_seconds",
                DEFAULT_EXTERNAL_EMBEDDING_TIMEOUT_SECONDS,
            )
        ),
        batch_size=int(
            getattr(
                settings,
                "embedding_batch_size",
                DEFAULT_EXTERNAL_EMBEDDING_BATCH_SIZE,
            )
        ),
        dimension=_coerce_optional_dimension(getattr(settings, "embedding_dimension", None)),
    )


def tokenize_text(text: str) -> list[str]:
    normalized = text.lower().strip()
    return TOKEN_PATTERN.findall(normalized)


def _coerce_embedding_index(item: object, *, fallback: int) -> int:
    if not isinstance(item, dict):
        return fallback
    value = item.get("index")
    if isinstance(value, int):
        return value
    return fallback


def _coerce_embedding_vector(values: list[object]) -> list[float]:
    vector: list[float] = []
    for value in values:
        if not isinstance(value, (int, float)):
            raise EmbeddingProviderError("Embedding vector contains non-numeric values.")
        vector.append(float(value))
    if not vector:
        raise EmbeddingProviderError("Embedding vector is empty.")
    return vector


def _normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise EmbeddingProviderError("Embedding vector could not be normalized.")
    return [value / magnitude for value in vector]


def _coerce_optional_dimension(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


@lru_cache(maxsize=4)
def _load_fastembed_model(
    *,
    model_name: str,
    cache_dir: str,
):
    TextEmbedding = _import_fastembed_text_embedding_class()
    try:
        return TextEmbedding(
            model_name=model_name,
            cache_dir=cache_dir or None,
            lazy_load=True,
        )
    except TypeError:
        try:
            return TextEmbedding(
                model_name=model_name,
                cache_dir=cache_dir or None,
            )
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Failed to load fastembed model '{model_name}'."
            ) from exc
    except Exception as exc:
        raise EmbeddingProviderError(
            f"Failed to load fastembed model '{model_name}'."
        ) from exc


@lru_cache(maxsize=4)
def _load_sentence_transformer_model(
    *,
    model_name: str,
    device: str,
    cache_dir: str,
):
    SentenceTransformer = _import_sentence_transformer_class()
    try:
        return SentenceTransformer(
            model_name_or_path=model_name,
            device=device or None,
            cache_folder=cache_dir or None,
        )
    except Exception as exc:
        raise EmbeddingProviderError(
            f"Failed to load sentence_transformers model '{model_name}' on device '{device or DEFAULT_SENTENCE_TRANSFORMERS_DEVICE}'."
        ) from exc


def _import_sentence_transformer_class():
    try:
        module = importlib.import_module("sentence_transformers")
    except ModuleNotFoundError as exc:
        raise EmbeddingProviderError(
            "sentence-transformers is not installed. Install dependencies and rebuild the environment.",
            error_code="EMBEDDING_PROVIDER_NOT_INSTALLED",
        ) from exc

    sentence_transformer_class = getattr(module, "SentenceTransformer", None)
    if sentence_transformer_class is None:
        raise EmbeddingProviderError(
            "sentence-transformers is installed, but SentenceTransformer could not be imported."
        )
    return sentence_transformer_class


def _import_fastembed_text_embedding_class():
    try:
        module = importlib.import_module("fastembed")
    except ModuleNotFoundError as exc:
        raise EmbeddingProviderError(
            "fastembed is not installed. Install the default embedding dependencies and rebuild the environment.",
            error_code="EMBEDDING_PROVIDER_NOT_INSTALLED",
        ) from exc

    text_embedding_class = getattr(module, "TextEmbedding", None)
    if text_embedding_class is None:
        raise EmbeddingProviderError("fastembed is installed, but TextEmbedding could not be imported.")
    return text_embedding_class


def _coerce_sentence_transformer_vectors(value: object) -> list[list[float]]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list):
        raise EmbeddingProviderError(
            "sentence_transformers provider returned vectors in an unexpected format."
        )

    vectors: list[list[float]] = []
    for item in value:
        if hasattr(item, "tolist"):
            item = item.tolist()
        if not isinstance(item, list):
            raise EmbeddingProviderError(
                "sentence_transformers provider returned an invalid vector row."
            )
        vectors.append(_coerce_embedding_vector(item))

    if not vectors:
        raise EmbeddingProviderError("sentence_transformers provider returned no vectors.")
    return vectors


def _coerce_fastembed_vectors(value: object) -> list[list[float]]:
    if not isinstance(value, list):
        raise EmbeddingProviderError("fastembed provider returned vectors in an unexpected format.")

    vectors: list[list[float]] = []
    for item in value:
        if hasattr(item, "tolist"):
            item = item.tolist()
        if not isinstance(item, list):
            raise EmbeddingProviderError("fastembed provider returned an invalid vector row.")
        vectors.append(_coerce_embedding_vector(item))

    if not vectors:
        raise EmbeddingProviderError("fastembed provider returned no vectors.")
    return vectors


def _prepare_fastembed_passage(text: str) -> str:
    normalized = text.strip()
    if normalized.startswith("passage: "):
        return normalized
    return f"passage: {normalized}"


def _prepare_fastembed_query(text: str) -> str:
    normalized = text.strip()
    if normalized.startswith("query: "):
        return normalized
    return f"query: {normalized}"
