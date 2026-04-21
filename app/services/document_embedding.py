from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import re

from app.models.document import Document
from app.models.enums import KnowledgeBaseScope
from app.services.document_chunker import build_chunk_relative_path


EMBEDDING_DIMENSION = 128
EMBEDDING_SCHEME = "hashed_bow_v1"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")

logger = logging.getLogger("purelink.documents")


class DocumentEmbeddingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EmbeddedDocumentResult:
    index_path: str
    embedded_chunk_count: int
    embedding_dimension: int


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    text: str
    score: float


def resolve_vector_store_root(vector_store_dir: str | Path, *, base_dir: Path) -> Path:
    vector_root = Path(vector_store_dir)
    if not vector_root.is_absolute():
        vector_root = base_dir / vector_root
    return vector_root


def embed_document_chunks(
    *,
    document: Document,
    chunks_root: Path,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
    dimension: int = EMBEDDING_DIMENSION,
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

    entries: list[dict[str, object]] = []
    for item in chunks:
        if not isinstance(item, dict):
            raise DocumentEmbeddingError("Document chunk result contains invalid chunk entries.")

        text = item.get("text")
        chunk_id = item.get("chunk_id")
        if not isinstance(text, str) or not isinstance(chunk_id, str):
            raise DocumentEmbeddingError("Document chunk entry is missing required fields.")

        entries.append(
            {
                "chunk_id": chunk_id,
                "document_id": document.id,
                "knowledge_base_id": document.knowledge_base_id,
                "scope": scope.value,
                "team_id": team_id,
                "text": text,
                "vector": build_text_embedding(text, dimension=dimension),
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
    payload["embedding_scheme"] = EMBEDDING_SCHEME
    payload["embedding_dimension"] = dimension
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
            "chunk_source_path": chunk_relative_path.as_posix(),
            "embedded_chunk_count": len(entries),
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
        embedding_dimension=dimension,
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
    query_vector = build_text_embedding(query, dimension=dimension)

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

            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    knowledge_base_id=knowledge_base_id,
                    scope=str(chunk.get("scope", scope.value)),
                    team_id=_coerce_optional_int(chunk.get("team_id")),
                    text=text,
                    score=score,
                )
            )

    results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return results[:top_k]


def build_text_embedding(text: str, *, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    tokens = tokenize_text(text)
    if not tokens:
        raise DocumentEmbeddingError("Text contains no tokens for embedding.")

    vector = [0.0] * dimension
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise DocumentEmbeddingError("Text embedding could not be normalized.")
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Vector dimensions must match.")
    return sum(lhs * rhs for lhs, rhs in zip(left, right, strict=True))


def tokenize_text(text: str) -> list[str]:
    normalized = text.lower().strip()
    return TOKEN_PATTERN.findall(normalized)


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
