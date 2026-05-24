from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_index import DocumentIndex
from app.models.enums import DocumentIndexStatus, DocumentIndexType
from app.services.embedding_provider import resolve_configured_embedding_provider


logger = logging.getLogger("purelink.indexing")

LEGACY_UNKNOWN_INDEX_REASON = "legacy_unknown"
MISSING_INDEX_REASON = "missing_index"
STATUS_NOT_INDEXED_REASON = "status_not_indexed"
PROVIDER_MISMATCH_REASON = "provider_mismatch"
MODEL_MISMATCH_REASON = "model_mismatch"
DIMENSION_MISMATCH_REASON = "dimension_mismatch"


@dataclass(frozen=True, slots=True)
class VectorIndexCompatibilityDecision:
    document_id: int
    allowed: bool
    reason: str | None
    index_status: str | None = None
    index_provider: str | None = None
    index_model_name: str | None = None
    index_model_dim: int | None = None


def mark_vector_indexing(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
    provider: str,
    model_name: str,
    model_dim: int | None,
    model_version: str | None = None,
) -> DocumentIndex:
    index = _get_or_create_vector_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
    )
    _apply_index_identity(
        index,
        provider=provider,
        model_name=model_name,
        model_dim=model_dim,
        model_version=model_version,
    )
    index.status = DocumentIndexStatus.INDEXING
    index.error_message = None
    index.stale_reason = None
    index.indexed_at = None
    db.flush()
    return index


def mark_vector_indexed(
    db: Session,
    *,
    document_id: int,
    provider: str,
    model_name: str,
    model_dim: int | None,
    knowledge_base_id: int | None = None,
    model_version: str | None = None,
    indexed_at: datetime | None = None,
) -> DocumentIndex:
    index = _get_or_create_vector_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
    )
    _apply_index_identity(
        index,
        provider=provider,
        model_name=model_name,
        model_dim=model_dim,
        model_version=model_version,
    )
    index.status = DocumentIndexStatus.INDEXED
    index.error_message = None
    index.stale_reason = None
    index.indexed_at = indexed_at or datetime.now(UTC)
    db.flush()
    return index


def mark_vector_failed(
    db: Session,
    *,
    document_id: int,
    error_message: str,
    knowledge_base_id: int | None = None,
    provider: str | None = None,
    model_name: str | None = None,
    model_dim: int | None = None,
    model_version: str | None = None,
) -> DocumentIndex:
    index = _get_or_create_vector_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
    )
    if provider is not None and model_name is not None:
        _apply_index_identity(
            index,
            provider=provider,
            model_name=model_name,
            model_dim=model_dim,
            model_version=model_version,
        )
    index.status = DocumentIndexStatus.FAILED
    index.error_message = error_message
    index.stale_reason = None
    db.flush()
    return index


def mark_graph_indexing(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
    provider: str = "local_rule",
    model_name: str = "local_rule_graph_extractor",
    model_version: str | None = None,
) -> DocumentIndex:
    index = _get_or_create_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        index_type=DocumentIndexType.GRAPH,
    )
    _apply_index_identity(
        index,
        provider=provider,
        model_name=model_name,
        model_dim=None,
        model_version=model_version,
    )
    index.status = DocumentIndexStatus.INDEXING
    index.error_message = None
    index.stale_reason = None
    index.indexed_at = None
    db.flush()
    return index


def mark_graph_indexed(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
    provider: str = "local_rule",
    model_name: str = "local_rule_graph_extractor",
    model_version: str | None = None,
    indexed_at: datetime | None = None,
) -> DocumentIndex:
    index = _get_or_create_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        index_type=DocumentIndexType.GRAPH,
    )
    _apply_index_identity(
        index,
        provider=provider,
        model_name=model_name,
        model_dim=None,
        model_version=model_version,
    )
    index.status = DocumentIndexStatus.INDEXED
    index.error_message = None
    index.stale_reason = None
    index.indexed_at = indexed_at or datetime.now(UTC)
    db.flush()
    return index


def mark_graph_failed(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
    error_message: str,
    provider: str = "local_rule",
    model_name: str = "local_rule_graph_extractor",
    model_version: str | None = None,
) -> DocumentIndex:
    index = _get_or_create_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        index_type=DocumentIndexType.GRAPH,
    )
    _apply_index_identity(
        index,
        provider=provider,
        model_name=model_name,
        model_dim=None,
        model_version=model_version,
    )
    index.status = DocumentIndexStatus.FAILED
    index.error_message = error_message
    index.stale_reason = None
    db.flush()
    return index


def get_graph_index(db: Session, *, document_id: int) -> DocumentIndex | None:
    return db.scalar(
        select(DocumentIndex).where(
            DocumentIndex.document_id == document_id,
            DocumentIndex.index_type == DocumentIndexType.GRAPH,
        )
    )


def mark_vector_stale(
    db: Session,
    *,
    document_id: int,
    stale_reason: str,
) -> DocumentIndex | None:
    index = get_vector_index(db, document_id=document_id)
    if index is None:
        return None
    index.status = DocumentIndexStatus.STALE
    index.stale_reason = stale_reason
    db.flush()
    return index


def request_document_reindex(
    db: Session,
    *,
    document_id: int,
    index_type: DocumentIndexType = DocumentIndexType.VECTOR,
) -> DocumentIndex | None:
    if index_type != DocumentIndexType.VECTOR:
        raise ValueError("Only vector reindex requests are supported in M4.")

    index = get_vector_index(db, document_id=document_id)
    if index is None:
        return None
    index.status = DocumentIndexStatus.PENDING
    index.stale_reason = None
    index.error_message = None
    db.flush()
    return index


def get_vector_index(db: Session, *, document_id: int) -> DocumentIndex | None:
    return db.scalar(
        select(DocumentIndex).where(
            DocumentIndex.document_id == document_id,
            DocumentIndex.index_type == DocumentIndexType.VECTOR,
        )
    )


def is_vector_index_compatible(
    db: Session,
    *,
    document_id: int,
    current_provider: str,
    current_model_name: str,
    current_model_dim: int | None,
) -> tuple[bool, str | None]:
    index = get_vector_index(db, document_id=document_id)
    return check_vector_index_compatibility(
        index,
        current_provider=current_provider,
        current_model_name=current_model_name,
        current_model_dim=current_model_dim,
    )


def check_vector_index_compatibility(
    index: DocumentIndex | None,
    *,
    current_provider: str,
    current_model_name: str,
    current_model_dim: int | None,
) -> tuple[bool, str | None]:
    if index is None:
        return True, LEGACY_UNKNOWN_INDEX_REASON
    if index.status != DocumentIndexStatus.INDEXED:
        return False, STATUS_NOT_INDEXED_REASON
    if index.provider != current_provider:
        return False, PROVIDER_MISMATCH_REASON
    if index.model_name != current_model_name:
        return False, MODEL_MISMATCH_REASON
    if (
        index.model_dim is not None
        and current_model_dim is not None
        and index.model_dim != current_model_dim
    ):
        return False, DIMENSION_MISMATCH_REASON
    return True, None


def filter_documents_with_compatible_vector_index(
    db: Session,
    *,
    documents: Sequence[Document],
    current_provider: str,
    current_model_name: str,
    current_model_dim: int | None,
) -> list[Document]:
    decisions = evaluate_documents_vector_index_compatibility(
        db,
        documents=documents,
        current_provider=current_provider,
        current_model_name=current_model_name,
        current_model_dim=current_model_dim,
    )
    decision_by_document_id = {item.document_id: item for item in decisions}
    allowed: list[Document] = []
    for document in documents:
        decision = decision_by_document_id.get(document.id)
        if decision is None or decision.allowed:
            allowed.append(document)
            continue
        logger.info(
            "document vector index skipped document_id=%s knowledge_base_id=%s reason=%s",
            document.id,
            document.knowledge_base_id,
            decision.reason,
        )
    return allowed


def evaluate_documents_vector_index_compatibility(
    db: Session,
    *,
    documents: Sequence[Document],
    current_provider: str,
    current_model_name: str,
    current_model_dim: int | None,
) -> list[VectorIndexCompatibilityDecision]:
    if not documents:
        return []

    document_ids = [item.id for item in documents]
    indexes = {
        item.document_id: item
        for item in db.scalars(
            select(DocumentIndex).where(
                DocumentIndex.document_id.in_(document_ids),
                DocumentIndex.index_type == DocumentIndexType.VECTOR,
            )
        )
    }
    decisions: list[VectorIndexCompatibilityDecision] = []
    for document in documents:
        index = indexes.get(document.id)
        compatible, reason = check_vector_index_compatibility(
            index,
            current_provider=current_provider,
            current_model_name=current_model_name,
            current_model_dim=current_model_dim,
        )
        decisions.append(
            VectorIndexCompatibilityDecision(
                document_id=document.id,
                allowed=compatible,
                reason=reason,
                index_status=index.status.value if index is not None else None,
                index_provider=index.provider if index is not None else None,
                index_model_name=index.model_name if index is not None else None,
                index_model_dim=index.model_dim if index is not None else None,
            )
        )
    return decisions


def list_stale_indexes_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
    current_provider: str,
    current_model_name: str,
    current_model_dim: int | None,
) -> list[DocumentIndex]:
    indexes = list(
        db.scalars(
            select(DocumentIndex)
            .where(
                DocumentIndex.knowledge_base_id == knowledge_base_id,
                DocumentIndex.index_type == DocumentIndexType.VECTOR,
            )
            .order_by(DocumentIndex.document_id.asc())
        )
    )
    stale: list[DocumentIndex] = []
    for index in indexes:
        compatible, reason = check_vector_index_compatibility(
            index,
            current_provider=current_provider,
            current_model_name=current_model_name,
            current_model_dim=current_model_dim,
        )
        if compatible:
            continue
        index.stale_reason = reason
        if index.status == DocumentIndexStatus.INDEXED:
            index.status = DocumentIndexStatus.STALE
        stale.append(index)
    db.flush()
    return stale


def get_vector_index_identity_from_settings(
    settings: object,
) -> tuple[str, str, int | None, str | None]:
    provider = resolve_configured_embedding_provider(settings)
    configured_dimension = getattr(settings, "embedding_dimension", None)
    model_dim = (
        provider.default_dimension
        if provider.default_dimension and provider.default_dimension > 0
        else configured_dimension
    )
    return provider.provider_name, provider.model, model_dim, provider.version


def _get_or_create_vector_index(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
) -> DocumentIndex:
    index = get_vector_index(db, document_id=document_id)
    if index is not None:
        if knowledge_base_id is not None:
            index.knowledge_base_id = knowledge_base_id
        return index
    return _create_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        index_type=DocumentIndexType.VECTOR,
    )


def _get_or_create_index(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
    index_type: DocumentIndexType,
) -> DocumentIndex:
    index = db.scalar(
        select(DocumentIndex).where(
            DocumentIndex.document_id == document_id,
            DocumentIndex.index_type == index_type,
        )
    )
    if index is not None:
        if knowledge_base_id is not None:
            index.knowledge_base_id = knowledge_base_id
        return index

    return _create_index(
        db,
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        index_type=index_type,
    )


def _create_index(
    db: Session,
    *,
    document_id: int,
    knowledge_base_id: int | None,
    index_type: DocumentIndexType,
) -> DocumentIndex:
    resolved_knowledge_base_id = knowledge_base_id or _resolve_document_knowledge_base_id(
        db,
        document_id=document_id,
    )
    index = DocumentIndex(
        document_id=document_id,
        knowledge_base_id=resolved_knowledge_base_id,
        index_type=index_type,
        provider="unknown",
        model_name="unknown",
        status=DocumentIndexStatus.PENDING,
    )
    db.add(index)
    return index


def _resolve_document_knowledge_base_id(db: Session, *, document_id: int) -> int:
    knowledge_base_id = db.scalar(
        select(Document.knowledge_base_id).where(Document.id == document_id)
    )
    if knowledge_base_id is None:
        raise ValueError("Document does not exist.")
    return knowledge_base_id


def _apply_index_identity(
    index: DocumentIndex,
    *,
    provider: str,
    model_name: str,
    model_dim: int | None,
    model_version: str | None,
) -> None:
    index.provider = provider
    index.model_name = model_name
    index.model_dim = model_dim
    index.model_version = model_version
