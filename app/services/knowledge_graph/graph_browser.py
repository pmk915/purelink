from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.services.chunk_metadata import parse_chunk_metadata
from app.schemas.knowledge_graph import (
    KnowledgeGraphEntityDetailRead,
    KnowledgeGraphEntityListRead,
    KnowledgeGraphEntitySummaryRead,
    KnowledgeGraphMentionRead,
    KnowledgeGraphRelationRead,
)


def list_graph_entities(
    db: Session,
    *,
    knowledge_base_id: int,
    query: str | None = None,
    limit: int = 50,
) -> KnowledgeGraphEntityListRead:
    statement = select(KnowledgeEntity).where(
        KnowledgeEntity.knowledge_base_id == knowledge_base_id
    )
    normalized_query = (query or "").strip()
    if normalized_query:
        like_query = f"%{normalized_query.casefold()}%"
        statement = statement.where(
            or_(
                func.lower(KnowledgeEntity.name).like(like_query),
                func.lower(KnowledgeEntity.normalized_name).like(like_query),
            )
        )
    statement = statement.order_by(KnowledgeEntity.name.asc()).limit(limit)
    entities = list(db.scalars(statement))
    return KnowledgeGraphEntityListRead(
        items=[
            _build_entity_summary(db, entity=entity)
            for entity in entities
        ]
    )


def get_graph_entity_detail(
    db: Session,
    *,
    knowledge_base_id: int,
    entity_id: int,
) -> KnowledgeGraphEntityDetailRead | None:
    entity = db.scalar(
        select(KnowledgeEntity).where(
            KnowledgeEntity.id == entity_id,
            KnowledgeEntity.knowledge_base_id == knowledge_base_id,
        )
    )
    if entity is None:
        return None

    summary = _build_entity_summary(db, entity=entity)
    mentions = [
        _build_mention_read(mention)
        for mention in db.scalars(
            select(EntityMention)
            .where(
                EntityMention.knowledge_base_id == knowledge_base_id,
                EntityMention.entity_id == entity.id,
            )
            .order_by(EntityMention.id.asc())
            .limit(50)
        )
    ]
    relations = [
        _build_relation_read(relation)
        for relation in db.scalars(
            select(KnowledgeRelation)
            .where(
                KnowledgeRelation.knowledge_base_id == knowledge_base_id,
                or_(
                    KnowledgeRelation.source_entity_id == entity.id,
                    KnowledgeRelation.target_entity_id == entity.id,
                ),
            )
            .order_by(KnowledgeRelation.id.asc())
            .limit(80)
        )
    ]
    return KnowledgeGraphEntityDetailRead(
        **summary.model_dump(),
        mentions=mentions,
        relations=relations,
    )


def _build_entity_summary(
    db: Session,
    *,
    entity: KnowledgeEntity,
) -> KnowledgeGraphEntitySummaryRead:
    mention_count = db.scalar(
        select(func.count(EntityMention.id)).where(EntityMention.entity_id == entity.id)
    )
    relation_count = db.scalar(
        select(func.count(KnowledgeRelation.id)).where(
            or_(
                KnowledgeRelation.source_entity_id == entity.id,
                KnowledgeRelation.target_entity_id == entity.id,
            )
        )
    )
    return KnowledgeGraphEntitySummaryRead(
        id=entity.id,
        name=entity.name,
        entity_type=entity.entity_type,
        description=entity.description,
        mention_count=int(mention_count or 0),
        relation_count=int(relation_count or 0),
    )


def _build_mention_read(mention: EntityMention) -> KnowledgeGraphMentionRead:
    return KnowledgeGraphMentionRead(
        document_id=mention.document_id,
        document_name=mention.document.original_filename if mention.document else None,
        chunk_id=mention.chunk_id,
        citation_unit_id=mention.citation_unit_id,
        source_locator=mention.source_locator,
        text_span=mention.text_span,
    )


def _build_relation_read(relation: KnowledgeRelation) -> KnowledgeGraphRelationRead:
    source_locator = None
    if relation.source_citation_unit is not None:
        source_locator = parse_chunk_metadata(
            relation.source_citation_unit.metadata_json
        ).source_locator
    elif relation.source_chunk is not None:
        source_locator = parse_chunk_metadata(relation.source_chunk.metadata_json).source_locator

    return KnowledgeGraphRelationRead(
        id=relation.id,
        source_entity_id=relation.source_entity_id,
        source_entity_name=relation.source_entity.name,
        target_entity_id=relation.target_entity_id,
        target_entity_name=relation.target_entity.name,
        relation_type=relation.relation_type,
        description=relation.description,
        source_document_id=relation.source_document_id,
        source_document_name=(
            relation.source_document.original_filename
            if isinstance(relation.source_document, Document)
            else None
        ),
        source_chunk_id=relation.source_chunk_id,
        source_citation_unit_id=relation.source_citation_unit_id,
        source_locator=source_locator,
        confidence=relation.confidence,
    )
