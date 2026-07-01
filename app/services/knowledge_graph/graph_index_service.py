from __future__ import annotations

from dataclasses import dataclass
import logging

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.services.chunk_metadata import parse_chunk_metadata
from app.services.indexing.index_metadata_service import (
    mark_graph_failed,
    mark_graph_indexed,
    mark_graph_indexing,
)
from app.services.knowledge_graph.graph_extractor import extract_graph_from_sources
from app.services.knowledge_graph.normalizer import normalize_entity_name
from app.services.knowledge_graph.types import ExtractedEntity, GraphSourceText


logger = logging.getLogger("purelink.knowledge_graph")

GRAPH_PROVIDER = "local_rule"
GRAPH_MODEL_NAME = "local_rule_graph_extractor"


@dataclass(frozen=True, slots=True)
class GraphIndexBuildResult:
    entity_count: int
    relation_count: int
    mention_count: int


@dataclass(frozen=True, slots=True)
class GraphCleanupResult:
    kb_id: int | None
    document_id: int | None = None
    deleted_mentions: int = 0
    deleted_relation_sources: int = 0
    deleted_relations: int = 0
    deleted_orphan_entities: int = 0


@dataclass(frozen=True, slots=True)
class GraphDeduplicationResult:
    kb_id: int
    merged_relations: int
    deleted_duplicate_relations: int


@dataclass(frozen=True, slots=True)
class GraphDocumentRebuildResult:
    document_id: int
    kb_id: int
    deleted_mentions: int
    deleted_relation_sources: int
    deleted_relations: int
    created_entities: int
    created_mentions: int
    created_relations: int
    deduplicated_relations: int
    deleted_orphan_entities: int


def build_document_graph_index(db: Session, *, document: Document) -> GraphIndexBuildResult:
    mark_graph_indexing(
        db,
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        provider=GRAPH_PROVIDER,
        model_name=GRAPH_MODEL_NAME,
    )
    try:
        delete_document_graph(db, document_id=document.id)
        result = _write_document_graph(db, document=document)
        deduplicate_relations(db, kb_id=document.knowledge_base_id)
        cleanup_orphan_entities(db, kb_id=document.knowledge_base_id)
        mark_graph_indexed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider=GRAPH_PROVIDER,
            model_name=GRAPH_MODEL_NAME,
        )
        db.flush()
        logger.info(
            "document graph index built document_id=%s knowledge_base_id=%s entity_count=%s relation_count=%s mention_count=%s",
            document.id,
            document.knowledge_base_id,
            result.entity_count,
            result.relation_count,
            result.mention_count,
        )
        return result
    except Exception as exc:
        mark_graph_failed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider=GRAPH_PROVIDER,
            model_name=GRAPH_MODEL_NAME,
            error_message=str(exc),
        )
        logger.exception(
            "document graph index failed document_id=%s knowledge_base_id=%s",
            document.id,
            document.knowledge_base_id,
        )
        return GraphIndexBuildResult(entity_count=0, relation_count=0, mention_count=0)


def delete_document_graph(db: Session, *, document_id: int) -> GraphCleanupResult:
    document = db.get(Document, document_id)
    kb_id = document.knowledge_base_id if document is not None else _find_graph_kb_id_for_document(
        db,
        document_id=document_id,
    )
    if kb_id is None:
        return GraphCleanupResult(kb_id=None, document_id=document_id)

    deleted_mentions = _rowcount(
        db.execute(delete(EntityMention).where(EntityMention.document_id == document_id))
    )

    chunk_ids = select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
    citation_unit_ids = select(DocumentCitationUnit.id).where(
        DocumentCitationUnit.document_id == document_id
    )
    deleted_relations = _rowcount(
        db.execute(
            delete(KnowledgeRelation)
            .where(
                KnowledgeRelation.knowledge_base_id == kb_id,
                or_(
                    KnowledgeRelation.source_document_id == document_id,
                    KnowledgeRelation.source_chunk_id.in_(chunk_ids),
                    KnowledgeRelation.source_citation_unit_id.in_(citation_unit_ids),
                ),
            )
            .execution_options(synchronize_session=False)
        )
    )
    orphan_result = cleanup_orphan_entities(db, kb_id=kb_id)
    db.flush()
    return GraphCleanupResult(
        kb_id=kb_id,
        document_id=document_id,
        deleted_mentions=deleted_mentions,
        deleted_relation_sources=deleted_relations,
        deleted_relations=deleted_relations,
        deleted_orphan_entities=orphan_result.deleted_orphan_entities,
    )


def cleanup_orphan_entities(db: Session, *, kb_id: int) -> GraphCleanupResult:
    deleted_orphans = 0
    entities = list(
        db.scalars(
            select(KnowledgeEntity).where(KnowledgeEntity.knowledge_base_id == kb_id)
        )
    )
    for entity in entities:
        mention_count = db.scalar(
            select(func.count(EntityMention.id)).where(
                EntityMention.knowledge_base_id == kb_id,
                EntityMention.entity_id == entity.id,
            )
        )
        outgoing_count = db.scalar(
            select(func.count(KnowledgeRelation.id)).where(
                KnowledgeRelation.knowledge_base_id == kb_id,
                KnowledgeRelation.source_entity_id == entity.id,
            )
        )
        incoming_count = db.scalar(
            select(func.count(KnowledgeRelation.id)).where(
                KnowledgeRelation.knowledge_base_id == kb_id,
                KnowledgeRelation.target_entity_id == entity.id,
            )
        )
        if not mention_count and not outgoing_count and not incoming_count:
            db.delete(entity)
            deleted_orphans += 1
    db.flush()
    return GraphCleanupResult(kb_id=kb_id, deleted_orphan_entities=deleted_orphans)


def deduplicate_relations(db: Session, *, kb_id: int) -> GraphDeduplicationResult:
    relations = list(
        db.scalars(
            select(KnowledgeRelation)
            .where(KnowledgeRelation.knowledge_base_id == kb_id)
            .order_by(KnowledgeRelation.id.asc())
        )
    )
    seen: set[tuple[int, int, str, str, int | None, int | None, int | None]] = set()
    deleted_duplicates = 0
    for relation in relations:
        key = (
            relation.source_entity_id,
            relation.target_entity_id,
            _normalize_relation_text(relation.relation_type),
            _normalize_relation_text(relation.description),
            relation.source_document_id,
            relation.source_chunk_id,
            relation.source_citation_unit_id,
        )
        if key in seen:
            db.delete(relation)
            deleted_duplicates += 1
            continue
        seen.add(key)
    db.flush()
    return GraphDeduplicationResult(
        kb_id=kb_id,
        merged_relations=deleted_duplicates,
        deleted_duplicate_relations=deleted_duplicates,
    )


def rebuild_document_graph(db: Session, *, document_id: int) -> GraphDocumentRebuildResult | None:
    document = db.get(Document, document_id)
    if document is None:
        return None

    mark_graph_indexing(
        db,
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        provider=GRAPH_PROVIDER,
        model_name=GRAPH_MODEL_NAME,
    )
    try:
        cleanup_result = delete_document_graph(db, document_id=document.id)
        build_result = _write_document_graph(db, document=document)
        dedupe_result = deduplicate_relations(db, kb_id=document.knowledge_base_id)
        orphan_result = cleanup_orphan_entities(db, kb_id=document.knowledge_base_id)
        mark_graph_indexed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider=GRAPH_PROVIDER,
            model_name=GRAPH_MODEL_NAME,
        )
        db.flush()
        return GraphDocumentRebuildResult(
            document_id=document.id,
            kb_id=document.knowledge_base_id,
            deleted_mentions=cleanup_result.deleted_mentions,
            deleted_relation_sources=cleanup_result.deleted_relation_sources,
            deleted_relations=cleanup_result.deleted_relations,
            created_entities=build_result.entity_count,
            created_mentions=build_result.mention_count,
            created_relations=build_result.relation_count,
            deduplicated_relations=dedupe_result.deleted_duplicate_relations,
            deleted_orphan_entities=(
                cleanup_result.deleted_orphan_entities
                + orphan_result.deleted_orphan_entities
            ),
        )
    except Exception as exc:
        mark_graph_failed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider=GRAPH_PROVIDER,
            model_name=GRAPH_MODEL_NAME,
            error_message=str(exc),
        )
        logger.exception(
            "document graph rebuild failed document_id=%s knowledge_base_id=%s",
            document.id,
            document.knowledge_base_id,
        )
        raise


def _write_document_graph(db: Session, *, document: Document) -> GraphIndexBuildResult:
    sources = _load_graph_source_texts(db, document=document)
    extraction = extract_graph_from_sources(sources)
    entity_by_normalized = {
        entity.normalized_name: _upsert_entity(
            db,
            knowledge_base_id=document.knowledge_base_id,
            entity=entity,
        )
        for entity in extraction.entities
    }

    mention_count = 0
    for mention in extraction.mentions:
        entity = entity_by_normalized.get(mention.normalized_name)
        if entity is None:
            continue
        db.add(
            EntityMention(
                entity_id=entity.id,
                knowledge_base_id=document.knowledge_base_id,
                document_id=mention.source_document_id,
                chunk_id=mention.source_chunk_id,
                citation_unit_id=mention.source_citation_unit_id,
                text_span=mention.text_span,
                source_locator=mention.source_locator,
            )
        )
        mention_count += 1

    relation_count = 0
    for relation in extraction.relations:
        source_entity = entity_by_normalized.get(normalize_entity_name(relation.source_name))
        target_entity = entity_by_normalized.get(normalize_entity_name(relation.target_name))
        if source_entity is None or target_entity is None or source_entity.id == target_entity.id:
            continue
        db.add(
            KnowledgeRelation(
                knowledge_base_id=document.knowledge_base_id,
                source_entity_id=source_entity.id,
                target_entity_id=target_entity.id,
                relation_type=relation.relation_type,
                description=relation.description,
                source_document_id=relation.source_document_id or document.id,
                source_chunk_id=relation.source_chunk_id,
                source_citation_unit_id=relation.source_citation_unit_id,
                confidence=relation.confidence,
            )
        )
        relation_count += 1

    db.flush()
    return GraphIndexBuildResult(
        entity_count=len(entity_by_normalized),
        relation_count=relation_count,
        mention_count=mention_count,
    )


def _load_graph_source_texts(db: Session, *, document: Document) -> list[GraphSourceText]:
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
    )
    if not chunks:
        return []

    units_by_chunk_id: dict[int, list[DocumentCitationUnit]] = {
        chunk.id: []
        for chunk in chunks
    }
    for unit in db.scalars(
        select(DocumentCitationUnit)
        .where(DocumentCitationUnit.document_id == document.id)
        .order_by(DocumentCitationUnit.unit_index.asc())
    ):
        units_by_chunk_id.setdefault(unit.chunk_id, []).append(unit)

    sources: list[GraphSourceText] = []
    for chunk in chunks:
        units = units_by_chunk_id.get(chunk.id) or []
        if not units:
            metadata = parse_chunk_metadata(chunk.metadata_json)
            sources.append(
                GraphSourceText(
                    document_id=document.id,
                    chunk_id=chunk.id,
                    citation_unit_id=None,
                    text=chunk.chunk_text,
                    source_locator=metadata.source_locator,
                )
            )
            continue
        for unit in units:
            metadata = parse_chunk_metadata(unit.metadata_json)
            sources.append(
                GraphSourceText(
                    document_id=document.id,
                    chunk_id=unit.chunk_id,
                    citation_unit_id=unit.id,
                    text=unit.unit_text,
                    source_locator=metadata.source_locator,
                )
            )
    return sources


def _upsert_entity(
    db: Session,
    *,
    knowledge_base_id: int,
    entity: ExtractedEntity,
) -> KnowledgeEntity:
    existing = db.scalar(
        select(KnowledgeEntity).where(
            KnowledgeEntity.knowledge_base_id == knowledge_base_id,
            KnowledgeEntity.normalized_name == entity.normalized_name,
        )
    )
    if existing is not None:
        if entity.confidence is not None and (
            existing.confidence is None or entity.confidence > existing.confidence
        ):
            existing.confidence = entity.confidence
            existing.name = entity.name
            existing.entity_type = entity.entity_type
            existing.description = entity.description
        db.flush()
        return existing

    created = KnowledgeEntity(
        knowledge_base_id=knowledge_base_id,
        name=entity.name,
        normalized_name=entity.normalized_name,
        entity_type=entity.entity_type,
        description=entity.description,
        confidence=entity.confidence,
    )
    db.add(created)
    db.flush()
    return created


def _find_graph_kb_id_for_document(db: Session, *, document_id: int) -> int | None:
    kb_id = db.scalar(
        select(EntityMention.knowledge_base_id)
        .where(EntityMention.document_id == document_id)
        .limit(1)
    )
    if kb_id is not None:
        return int(kb_id)
    kb_id = db.scalar(
        select(KnowledgeRelation.knowledge_base_id)
        .where(KnowledgeRelation.source_document_id == document_id)
        .limit(1)
    )
    return int(kb_id) if kb_id is not None else None


def _normalize_relation_text(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _rowcount(result: object) -> int:
    rowcount = getattr(result, "rowcount", 0)
    if rowcount is None or rowcount < 0:
        return 0
    return int(rowcount)
