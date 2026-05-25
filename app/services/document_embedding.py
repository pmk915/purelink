from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import KnowledgeBaseScope
from app.services.chunk_metadata import (
    build_chunk_snippet,
    infer_source_type_from_filename,
    parse_chunk_metadata,
)
from app.services.document_chunker import build_chunk_relative_path
from app.services.embedding_provider import (
    DEFAULT_EMBEDDING_DIMENSION,
    HASHED_BOW_SCHEME,
    EmbeddingProvider,
    EmbeddingProviderError,
    resolve_configured_embedding_provider,
    resolve_embedding_provider,
    tokenize_text as provider_tokenize_text,
)


EMBEDDING_DIMENSION = DEFAULT_EMBEDDING_DIMENSION
EMBEDDING_SCHEME = HASHED_BOW_SCHEME
INDEX_SCHEME = "json_vector_index_v1"
KB_REINDEX_REQUIRED_ERROR_CODE = "KNOWLEDGE_BASE_REINDEX_REQUIRED"

logger = logging.getLogger("purelink.documents")


class DocumentEmbeddingError(ValueError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class EmbeddedDocumentResult:
    index_path: str
    embedded_chunk_count: int
    embedding_dimension: int
    index_scheme: str
    embedding_scheme: str
    embedding_provider: str
    embedding_model: str
    embedding_version: str
    embedding_normalize: bool
    indexed_at: datetime


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    document_name: str
    text: str
    snippet: str
    source_type: str | None
    char_start: int | None
    char_end: int | None
    page_number: int | None
    start_time: float | None
    end_time: float | None
    section_title: str | None
    source_locator: str | None
    heading_path: tuple[str, ...] | None
    score: float
    chunk_db_id: int | None = None
    vector_score: float | None = None
    keyword_score: float | None = None
    graph_score: float | None = None
    matched_terms: tuple[str, ...] | None = None
    candidate_sources: tuple[str, ...] | None = None
    ocr_provider: str | None = None
    ocr_provider_version: str | None = None
    asr_provider: str | None = None
    asr_provider_version: str | None = None


@dataclass(frozen=True, slots=True)
class IndexChunkInput:
    chunk_id: str
    text: str
    metadata: dict[str, object] | None = None
    chunk_db_id: int | None = None


def resolve_vector_store_root(vector_store_dir: str | Path, *, base_dir: Path) -> Path:
    vector_root = Path(vector_store_dir)
    if not vector_root.is_absolute():
        vector_root = base_dir / vector_root
    return vector_root


def delete_knowledge_base_index_artifact(
    *,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    team_id: int | None = None,
) -> bool:
    index_relative_path = build_index_relative_path(
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        team_id=team_id,
    )
    index_source = vector_root / index_relative_path
    if not index_source.exists():
        return False
    index_source.unlink()
    return True


def delete_document_from_knowledge_base_index(
    *,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    document_id: int,
    team_id: int | None = None,
) -> bool:
    index_relative_path = build_index_relative_path(
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        team_id=team_id,
    )
    index_source = vector_root / index_relative_path
    if not index_source.exists():
        return False

    payload = _load_index_payload(index_source)
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        raise DocumentEmbeddingError("Vector index is not valid.")

    remaining_documents = [
        item
        for item in documents
        if not isinstance(item, dict) or item.get("document_id") != document_id
    ]
    if len(remaining_documents) == len(documents):
        return False

    if not remaining_documents:
        index_source.unlink(missing_ok=True)
        return True

    payload["documents"] = remaining_documents
    payload["indexed_at"] = datetime.now(UTC).isoformat()
    index_source.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def read_knowledge_base_index_metadata(
    *,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    team_id: int | None = None,
) -> dict[str, object] | None:
    index_relative_path = build_index_relative_path(
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        team_id=team_id,
    )
    index_source = vector_root / index_relative_path
    if not index_source.exists():
        return None

    payload = _load_index_payload(index_source)
    return {
        "embedding_scheme": payload.get("embedding_scheme"),
        "embedding_provider": payload.get("embedding_provider"),
        "embedding_model": payload.get("embedding_model"),
        "embedding_version": payload.get("embedding_version"),
        "embedding_dimension": payload.get("embedding_dimension"),
        "embedding_normalize": payload.get("embedding_normalize"),
        "created_at": payload.get("created_at"),
        "indexed_at": payload.get("indexed_at"),
        "index_artifact_path": payload.get("index_artifact_path"),
    }


def embed_document_chunks(
    *,
    document: Document,
    chunks_root: Path,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
    dimension: int | None = None,
    provider: EmbeddingProvider | None = None,
) -> EmbeddedDocumentResult:
    chunk_relative_path = build_chunk_relative_path(
        scope=scope,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        team_id=team_id,
    )
    chunk_source = chunks_root / chunk_relative_path
    logger.info(
        "embed start document_id=%s knowledge_base_id=%s scope=%s team_id=%s chunk_source=%s dimension=%s",
        document.id,
        document.knowledge_base_id,
        scope.value,
        team_id,
        chunk_source,
        dimension,
    )
    if not chunk_source.exists():
        logger.error(
            "embed chunk source missing document_id=%s chunk_source=%s",
            document.id,
            chunk_source,
        )
        raise DocumentEmbeddingError("Document chunk result does not exist.")

    try:
        chunk_payload = json.loads(chunk_source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.exception(
            "embed chunk payload invalid document_id=%s chunk_source=%s",
            document.id,
            chunk_source,
        )
        raise DocumentEmbeddingError("Document chunk result is not valid JSON.") from exc

    chunks = chunk_payload.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        logger.error(
            "embed chunk payload missing chunks document_id=%s chunk_source=%s",
            document.id,
            chunk_source,
        )
        raise DocumentEmbeddingError("Document chunk result does not contain chunks.")

    chunk_inputs: list[IndexChunkInput] = []
    for item in chunks:
        if not isinstance(item, dict):
            raise DocumentEmbeddingError("Document chunk result contains invalid chunk entries.")

        text = item.get("text")
        chunk_id = item.get("chunk_id")
        if not isinstance(text, str) or not isinstance(chunk_id, str):
            raise DocumentEmbeddingError("Document chunk entry is missing required fields.")

        metadata = item.get("metadata")
        chunk_inputs.append(
            IndexChunkInput(
                chunk_db_id=None,
                chunk_id=chunk_id,
                text=text,
                metadata=metadata if isinstance(metadata, dict) else None,
            )
        )

    return _write_document_chunks_to_index(
        document=document,
        chunk_inputs=chunk_inputs,
        vector_root=vector_root,
        scope=scope,
        team_id=team_id,
        dimension=dimension,
        provider=provider,
        source_reference=chunk_relative_path.as_posix(),
    )


def embed_ready_document_chunks(
    db: Session,
    *,
    document: Document,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
    dimension: int | None = None,
    provider: EmbeddingProvider | None = None,
) -> EmbeddedDocumentResult:
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    saved_chunks = list(db.scalars(statement))
    if not saved_chunks:
        raise DocumentEmbeddingError("Document chunk records do not exist.")

    fallback_source_type = infer_source_type_from_filename(document.original_filename)
    chunk_inputs = [
        IndexChunkInput(
            chunk_db_id=item.id,
            chunk_id=item.chunk_key,
            text=item.chunk_text,
            metadata=_serialize_chunk_metadata_for_index(
                item.metadata_json,
                fallback_source_type=fallback_source_type,
            ),
        )
        for item in saved_chunks
    ]
    return _write_document_chunks_to_index(
        document=document,
        chunk_inputs=chunk_inputs,
        vector_root=vector_root,
        scope=scope,
        team_id=team_id,
        dimension=dimension,
        provider=provider,
        source_reference=f"document_chunks:{document.id}",
    )


def search_index(
    *,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    query: str,
    top_k: int,
    team_id: int | None = None,
    allowed_document_ids: set[int] | None = None,
    document_lookup: dict[int, Document] | None = None,
) -> list[RetrievedChunk]:
    index_relative_path = build_index_relative_path(
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        team_id=team_id,
    )
    index_source = vector_root / index_relative_path
    if not index_source.exists():
        return []

    payload = _load_index_payload(index_source)
    dimension = int(payload.get("embedding_dimension", EMBEDDING_DIMENSION))
    scheme = _coerce_optional_str(payload.get("embedding_scheme")) or EMBEDDING_SCHEME
    provider = _resolve_provider(scheme)
    query_vector = build_query_embedding(
        query,
        dimension=dimension,
        provider=provider,
    )
    _validate_index_provider_compatibility(
        payload,
        provider=provider,
        query_dimension=len(query_vector),
    )

    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        raise DocumentEmbeddingError("Vector index is not valid.")

    results: list[RetrievedChunk] = []
    for document_entry in documents:
        if not isinstance(document_entry, dict):
            continue

        document_id = document_entry.get("document_id")
        if not isinstance(document_id, int):
            continue
        if allowed_document_ids is not None and document_id not in allowed_document_ids:
            continue

        document_name = _resolve_document_name(
            document_id=document_id,
            document_entry=document_entry,
            document_lookup=document_lookup,
        )
        fallback_source_type = infer_source_type_from_filename(document_name)

        chunks = document_entry.get("chunks", [])
        if not isinstance(chunks, list):
            continue

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue

            chunk_id = chunk.get("chunk_id")
            text = chunk.get("text")
            vector = chunk.get("vector")
            if not isinstance(chunk_id, str) or not isinstance(text, str) or not isinstance(vector, list):
                continue

            score = cosine_similarity(query_vector, _coerce_vector(vector))
            if score <= 0:
                continue

            chunk_metadata = parse_chunk_metadata(
                chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else None,
                fallback_source_type=fallback_source_type,
            )
            results.append(
                RetrievedChunk(
                    chunk_db_id=_coerce_optional_int(chunk.get("chunk_db_id")),
                    chunk_id=chunk_id,
                    document_id=document_id,
                    knowledge_base_id=knowledge_base_id,
                    scope=_coerce_optional_str(chunk.get("scope")) or scope.value,
                    team_id=_coerce_optional_int(chunk.get("team_id")),
                    document_name=document_name,
                    text=text,
                    snippet=build_chunk_snippet(text),
                    source_type=chunk_metadata.source_type,
                    char_start=chunk_metadata.char_start,
                    char_end=chunk_metadata.char_end,
                    page_number=chunk_metadata.page_number,
                    start_time=chunk_metadata.start_time,
                    end_time=chunk_metadata.end_time,
                    section_title=chunk_metadata.section_title,
                    source_locator=chunk_metadata.source_locator,
                    heading_path=chunk_metadata.heading_path,
                    score=score,
                    vector_score=score,
                    candidate_sources=("vector",),
                    ocr_provider=chunk_metadata.ocr_provider,
                    ocr_provider_version=chunk_metadata.ocr_provider_version,
                    asr_provider=chunk_metadata.asr_provider,
                    asr_provider_version=chunk_metadata.asr_provider_version,
                )
            )

    results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return results[:top_k]


def build_text_embedding(
    text: str,
    *,
    dimension: int | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[float]:
    active_provider = provider or _resolve_provider(None)
    try:
        return active_provider.embed_text(text, dimension=dimension)
    except EmbeddingProviderError as exc:
        raise DocumentEmbeddingError(str(exc), error_code=getattr(exc, "error_code", None)) from exc


def build_query_embedding(
    text: str,
    *,
    dimension: int | None = None,
    provider: EmbeddingProvider | None = None,
) -> list[float]:
    active_provider = provider or _resolve_provider(None)
    try:
        return active_provider.embed_query(text, dimension=dimension)
    except EmbeddingProviderError as exc:
        raise DocumentEmbeddingError(str(exc), error_code=getattr(exc, "error_code", None)) from exc


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vector dimensions must match.")
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(lhs * rhs for lhs, rhs in zip(left, right, strict=True)) / (left_norm * right_norm)


def tokenize_text(text: str) -> list[str]:
    return provider_tokenize_text(text)


def build_index_relative_path(
    *,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    team_id: int | None = None,
) -> Path:
    if scope == KnowledgeBaseScope.PERSONAL:
        return Path("personal") / f"knowledge_base_{knowledge_base_id}" / "index.json"

    if team_id is None:
        raise ValueError("team_id is required for team vector index.")

    return (
        Path("team")
        / f"team_{team_id}"
        / f"knowledge_base_{knowledge_base_id}"
        / "index.json"
    )


def _write_document_chunks_to_index(
    *,
    document: Document,
    chunk_inputs: list[IndexChunkInput],
    vector_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None,
    dimension: int | None,
    provider: EmbeddingProvider | None,
    source_reference: str,
) -> EmbeddedDocumentResult:
    active_provider = provider or _resolve_provider(None)
    active_dimension = dimension or active_provider.default_dimension or None
    texts = [chunk.text for chunk in chunk_inputs]
    try:
        vectors = active_provider.embed_texts(texts, dimension=active_dimension)
    except EmbeddingProviderError as exc:
        raise DocumentEmbeddingError(str(exc), error_code=getattr(exc, "error_code", None)) from exc
    if len(vectors) != len(chunk_inputs):
        raise DocumentEmbeddingError("Embedding provider returned an invalid number of vectors.")
    embedding_dimension = len(vectors[0]) if vectors else active_dimension or EMBEDDING_DIMENSION

    entries: list[dict[str, object]] = []
    fallback_source_type = infer_source_type_from_filename(document.original_filename)
    for chunk, vector in zip(chunk_inputs, vectors, strict=True):
        if len(vector) != embedding_dimension:
            raise DocumentEmbeddingError("Embedding provider returned inconsistent vector dimensions.")
        entries.append(
            {
                "chunk_db_id": chunk.chunk_db_id,
                "chunk_id": chunk.chunk_id,
                "document_id": document.id,
                "knowledge_base_id": document.knowledge_base_id,
                "scope": scope.value,
                "team_id": team_id,
                "text": chunk.text,
                "metadata": _serialize_chunk_metadata_for_index(
                    chunk.metadata,
                    fallback_source_type=fallback_source_type,
                ),
                "vector": vector,
            }
        )

    index_relative_path = build_index_relative_path(
        scope=scope,
        knowledge_base_id=document.knowledge_base_id,
        team_id=team_id,
    )
    destination = vector_root / index_relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = _load_index_payload(destination)
    indexed_at = datetime.now(UTC)
    mismatch_reason = _describe_single_document_reindex_mismatch(
        payload,
        document_id=document.id,
        provider=active_provider,
        embedding_dimension=embedding_dimension,
    )
    if mismatch_reason is not None:
        raise DocumentEmbeddingError(
            mismatch_reason,
            error_code=KB_REINDEX_REQUIRED_ERROR_CODE,
        )

    existing_document_entry = _find_index_document_entry(payload, document_id=document.id)
    created_at = _coerce_optional_str(payload.get("created_at")) or indexed_at.isoformat()
    payload["embedding_scheme"] = active_provider.scheme
    payload["embedding_provider"] = active_provider.provider_name
    payload["embedding_model"] = active_provider.model
    payload["embedding_version"] = active_provider.version
    payload["embedding_dimension"] = embedding_dimension
    payload["embedding_normalize"] = bool(getattr(active_provider, "normalize", True))
    payload["created_at"] = created_at
    payload["index_scheme"] = INDEX_SCHEME
    payload["indexed_at"] = indexed_at.isoformat()
    payload["index_artifact_path"] = index_relative_path.as_posix()
    payload["scope"] = scope.value
    payload["team_id"] = team_id
    payload["knowledge_base_id"] = document.knowledge_base_id
    payload["documents"] = [
        item
        for item in payload.get("documents", [])
        if isinstance(item, dict) and item.get("document_id") != document.id
    ]
    payload["documents"].append(
        {
            "document_id": document.id,
            "document_name": document.original_filename,
            "chunk_source_path": source_reference,
            "embedded_chunk_count": len(entries),
            "index_scheme": INDEX_SCHEME,
            "embedding_scheme": active_provider.scheme,
            "embedding_provider": active_provider.provider_name,
            "embedding_model": active_provider.model,
            "embedding_version": active_provider.version,
            "embedding_dimension": embedding_dimension,
            "embedding_normalize": bool(getattr(active_provider, "normalize", True)),
            "created_at": _coerce_optional_str(
                existing_document_entry.get("created_at") if existing_document_entry else None
            )
            or indexed_at.isoformat(),
            "indexed_at": indexed_at.isoformat(),
            "index_artifact_path": index_relative_path.as_posix(),
            "chunks": entries,
        }
    )
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "embed completed document_id=%s destination=%s embedded_chunk_count=%s",
        document.id,
        destination,
        len(entries),
    )

    return EmbeddedDocumentResult(
        index_path=index_relative_path.as_posix(),
        embedded_chunk_count=len(entries),
        embedding_dimension=embedding_dimension,
        index_scheme=INDEX_SCHEME,
        embedding_scheme=active_provider.scheme,
        embedding_provider=active_provider.provider_name,
        embedding_model=active_provider.model,
        embedding_version=active_provider.version,
        embedding_normalize=bool(getattr(active_provider, "normalize", True)),
        indexed_at=indexed_at,
    )


def _load_index_payload(index_source: Path) -> dict[str, object]:
    if not index_source.exists():
        return {"documents": []}

    try:
        payload = json.loads(index_source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DocumentEmbeddingError("Vector index is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise DocumentEmbeddingError("Vector index is not valid.")
    return payload


def _coerce_vector(values: list[object]) -> list[float]:
    vector: list[float] = []
    for item in values:
        if not isinstance(item, (int, float)):
            raise DocumentEmbeddingError("Vector index contains invalid vector data.")
        vector.append(float(item))
    return vector


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        return None
    return value


def _coerce_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _find_index_document_entry(
    payload: dict[str, object],
    *,
    document_id: int,
) -> dict[str, object] | None:
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        return None
    for item in documents:
        if isinstance(item, dict) and item.get("document_id") == document_id:
            return item
    return None


def _resolve_provider(scheme: str | None) -> EmbeddingProvider:
    settings = get_settings()
    try:
        if scheme is None:
            return resolve_configured_embedding_provider(settings)
        return resolve_embedding_provider(
            scheme,
            api_base=settings.embedding_api_base,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            device=settings.embedding_device,
            normalize=settings.embedding_normalize,
            cache_dir=settings.embedding_model_cache_dir,
            timeout_seconds=settings.embedding_timeout_seconds,
            batch_size=settings.embedding_batch_size,
            dimension=settings.embedding_dimension,
        )
    except EmbeddingProviderError as exc:
        raise DocumentEmbeddingError(str(exc), error_code=getattr(exc, "error_code", None)) from exc


def _validate_index_provider_compatibility(
    payload: dict[str, object],
    *,
    provider: EmbeddingProvider,
    query_dimension: int | None = None,
) -> None:
    mismatch_reason = describe_index_metadata_mismatch(
        payload,
        provider=provider,
        query_dimension=query_dimension,
    )
    if mismatch_reason is not None:
        raise DocumentEmbeddingError(mismatch_reason)


def describe_index_metadata_mismatch(
    payload: dict[str, object],
    *,
    provider: EmbeddingProvider,
    query_dimension: int | None = None,
) -> str | None:
    mixed_fields = _find_mixed_document_metadata_fields(payload)
    if mixed_fields:
        return (
            "Knowledge base index contains mixed embedding metadata "
            f"({', '.join(mixed_fields)}). Reindex the knowledge base."
        )

    mismatched_fields: list[str] = []
    artifact_provider = _coerce_optional_str(payload.get("embedding_provider"))
    if artifact_provider and artifact_provider != provider.provider_name:
        mismatched_fields.append("embedding_provider")

    artifact_model = _coerce_optional_str(payload.get("embedding_model"))
    if artifact_model and provider.model and artifact_model != provider.model:
        mismatched_fields.append("embedding_model")

    artifact_dimension = _coerce_optional_int(payload.get("embedding_dimension"))
    if artifact_dimension is not None and query_dimension is not None and artifact_dimension != query_dimension:
        mismatched_fields.append("embedding_dimension")

    artifact_normalize = _coerce_optional_bool(payload.get("embedding_normalize"))
    provider_normalize = bool(getattr(provider, "normalize", True))
    if artifact_normalize is not None and artifact_normalize != provider_normalize:
        mismatched_fields.append("embedding_normalize")

    if not mismatched_fields:
        return None

    return (
        "Embedding configuration changed for this index "
        f"({', '.join(mismatched_fields)}). Reindex is required."
    )


def _describe_single_document_reindex_mismatch(
    payload: dict[str, object],
    *,
    document_id: int,
    provider: EmbeddingProvider,
    embedding_dimension: int,
) -> str | None:
    documents = payload.get("documents", [])
    if not isinstance(documents, list) or not documents:
        return None

    has_other_documents = any(
        isinstance(item, dict) and item.get("document_id") != document_id
        for item in documents
    )
    if not has_other_documents:
        return None

    mismatch_reason = describe_index_metadata_mismatch(
        payload,
        provider=provider,
        query_dimension=embedding_dimension,
    )
    if mismatch_reason is None:
        return None

    return (
        "Knowledge base index uses different embedding metadata. "
        "Reindex the knowledge base instead of a single document."
    )


def _find_mixed_document_metadata_fields(payload: dict[str, object]) -> list[str]:
    documents = payload.get("documents", [])
    if not isinstance(documents, list):
        return []

    top_level_metadata = {
        "embedding_provider": _coerce_optional_str(payload.get("embedding_provider")),
        "embedding_model": _coerce_optional_str(payload.get("embedding_model")),
        "embedding_dimension": _coerce_optional_int(payload.get("embedding_dimension")),
        "embedding_normalize": _coerce_optional_bool(payload.get("embedding_normalize")),
    }
    mismatched_fields: set[str] = set()

    for item in documents:
        if not isinstance(item, dict):
            continue
        for field_name, top_level_value in top_level_metadata.items():
            if top_level_value is None:
                continue
            if item.get(field_name) != top_level_value:
                mismatched_fields.add(field_name)

    return sorted(mismatched_fields)


def _resolve_document_name(
    *,
    document_id: int,
    document_entry: dict[str, object],
    document_lookup: dict[int, Document] | None,
) -> str:
    payload_name = _coerce_optional_str(document_entry.get("document_name"))
    if payload_name:
        return payload_name
    if document_lookup and document_id in document_lookup:
        return document_lookup[document_id].original_filename
    return f"document_{document_id}"


def _serialize_chunk_metadata_for_index(
    raw_metadata: str | dict[str, object] | None,
    *,
    fallback_source_type: str,
) -> dict[str, object]:
    metadata = parse_chunk_metadata(
        raw_metadata,
        fallback_source_type=fallback_source_type,
    )
    payload: dict[str, object] = {}
    if metadata.source_type:
        payload["source_type"] = metadata.source_type
    if metadata.char_start is not None:
        payload["char_start"] = metadata.char_start
    if metadata.char_end is not None:
        payload["char_end"] = metadata.char_end
    if metadata.page_number is not None:
        payload["page_number"] = metadata.page_number
    if metadata.start_time is not None:
        payload["start_time"] = metadata.start_time
    if metadata.end_time is not None:
        payload["end_time"] = metadata.end_time
    if metadata.section_title:
        payload["section_title"] = metadata.section_title
    if metadata.source_locator:
        payload["source_locator"] = metadata.source_locator
    if metadata.heading_path:
        payload["heading_path"] = list(metadata.heading_path)
    if metadata.ocr_provider:
        payload["ocr_provider"] = metadata.ocr_provider
    if metadata.ocr_provider_version:
        payload["ocr_provider_version"] = metadata.ocr_provider_version
    if metadata.ocr_language:
        payload["ocr_language"] = metadata.ocr_language
    if metadata.asr_provider:
        payload["asr_provider"] = metadata.asr_provider
    if metadata.asr_provider_version:
        payload["asr_provider_version"] = metadata.asr_provider_version
    if metadata.region_count is not None:
        payload["region_count"] = metadata.region_count
    if metadata.regions:
        payload["regions"] = [dict(item) for item in metadata.regions]
    return payload
