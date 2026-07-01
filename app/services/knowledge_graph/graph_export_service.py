from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.services.chunk_metadata import build_chunk_snippet


@dataclass(frozen=True, slots=True)
class GraphExportEntity:
    id: int
    name: str
    entity_type: str | None
    mention_count: int
    relation_count: int


@dataclass(frozen=True, slots=True)
class GraphExportRelationSource:
    document_id: int | None
    filename: str | None
    chunk_id: int | None
    citation_unit_id: int | None
    snippet: str | None


@dataclass(frozen=True, slots=True)
class GraphExportRelation:
    id: int
    source_entity: str
    target_entity: str
    source_entity_id: int
    target_entity_id: int
    type: str
    label: str | None
    source_count: int
    sources: list[GraphExportRelationSource]


@dataclass(frozen=True, slots=True)
class GraphExportResult:
    kb_id: int
    entities: list[GraphExportEntity]
    relations: list[GraphExportRelation]


def export_graph(
    db: Session,
    *,
    kb_id: int,
    entity_limit: int = 100,
    relation_limit: int = 300,
    sources_per_relation: int = 5,
) -> GraphExportResult:
    entity_limit = max(1, min(entity_limit, 500))
    relation_limit = max(1, min(relation_limit, 1000))
    sources_per_relation = max(1, min(sources_per_relation, 10))

    entities = [
        _build_export_entity(db, entity=entity)
        for entity in db.scalars(
            select(KnowledgeEntity)
            .where(KnowledgeEntity.knowledge_base_id == kb_id)
            .order_by(KnowledgeEntity.name.asc(), KnowledgeEntity.id.asc())
            .limit(entity_limit)
        )
    ]

    relation_rows = list(
        db.scalars(
            select(KnowledgeRelation)
            .where(KnowledgeRelation.knowledge_base_id == kb_id)
            .order_by(KnowledgeRelation.id.asc())
        )
    )
    grouped: dict[tuple[int, int, str, str], list[KnowledgeRelation]] = {}
    for relation in relation_rows:
        key = (
            relation.source_entity_id,
            relation.target_entity_id,
            _normalize_relation_text(relation.relation_type),
            _normalize_relation_text(relation.description),
        )
        grouped.setdefault(key, []).append(relation)

    relations = [
        _build_export_relation(
            items,
            sources_per_relation=sources_per_relation,
        )
        for items in grouped.values()
    ]
    relations.sort(key=lambda item: (item.source_entity.casefold(), item.target_entity.casefold(), item.id))

    return GraphExportResult(
        kb_id=kb_id,
        entities=entities,
        relations=relations[:relation_limit],
    )


def _build_export_entity(db: Session, *, entity: KnowledgeEntity) -> GraphExportEntity:
    mention_count = db.scalar(
        select(func.count(EntityMention.id)).where(
            EntityMention.knowledge_base_id == entity.knowledge_base_id,
            EntityMention.entity_id == entity.id,
        )
    )
    relation_count = db.scalar(
        select(func.count(KnowledgeRelation.id)).where(
            KnowledgeRelation.knowledge_base_id == entity.knowledge_base_id,
            or_(
                KnowledgeRelation.source_entity_id == entity.id,
                KnowledgeRelation.target_entity_id == entity.id,
            ),
        )
    )
    return GraphExportEntity(
        id=entity.id,
        name=entity.name,
        entity_type=entity.entity_type,
        mention_count=int(mention_count or 0),
        relation_count=int(relation_count or 0),
    )


def _build_export_relation(
    relations: list[KnowledgeRelation],
    *,
    sources_per_relation: int,
) -> GraphExportRelation:
    canonical = relations[0]
    return GraphExportRelation(
        id=canonical.id,
        source_entity=canonical.source_entity.name,
        target_entity=canonical.target_entity.name,
        source_entity_id=canonical.source_entity_id,
        target_entity_id=canonical.target_entity_id,
        type=canonical.relation_type,
        label=canonical.description,
        source_count=len(relations),
        sources=[
            _build_export_source(relation)
            for relation in relations[:sources_per_relation]
        ],
    )


def _build_export_source(relation: KnowledgeRelation) -> GraphExportRelationSource:
    filename = (
        relation.source_document.original_filename
        if isinstance(relation.source_document, Document)
        else None
    )
    text = None
    if relation.source_citation_unit is not None:
        text = relation.source_citation_unit.unit_text
    elif relation.source_chunk is not None:
        text = relation.source_chunk.chunk_text
    return GraphExportRelationSource(
        document_id=relation.source_document_id,
        filename=filename,
        chunk_id=relation.source_chunk_id,
        citation_unit_id=relation.source_citation_unit_id,
        snippet=build_chunk_snippet(text, max_length=240) if text else None,
    )


def _normalize_relation_text(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())
