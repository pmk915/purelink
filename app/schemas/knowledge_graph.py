from __future__ import annotations

from pydantic import BaseModel


class KnowledgeGraphEntitySummaryRead(BaseModel):
    id: int
    name: str
    entity_type: str | None = None
    description: str | None = None
    mention_count: int
    relation_count: int


class KnowledgeGraphEntityListRead(BaseModel):
    items: list[KnowledgeGraphEntitySummaryRead]


class KnowledgeGraphMentionRead(BaseModel):
    document_id: int
    document_name: str | None = None
    chunk_id: int | None = None
    citation_unit_id: int | None = None
    source_locator: str | None = None
    text_span: str | None = None


class KnowledgeGraphRelationRead(BaseModel):
    id: int
    source_entity_id: int
    source_entity_name: str
    target_entity_id: int
    target_entity_name: str
    relation_type: str
    description: str | None = None
    source_document_id: int | None = None
    source_document_name: str | None = None
    source_chunk_id: int | None = None
    source_citation_unit_id: int | None = None
    source_locator: str | None = None
    confidence: float | None = None


class KnowledgeGraphEntityDetailRead(KnowledgeGraphEntitySummaryRead):
    mentions: list[KnowledgeGraphMentionRead]
    relations: list[KnowledgeGraphRelationRead]


class KnowledgeGraphCleanupRead(BaseModel):
    kb_id: int | None
    document_id: int | None = None
    deleted_mentions: int = 0
    deleted_relation_sources: int = 0
    deleted_relations: int = 0
    deleted_orphan_entities: int = 0


class KnowledgeGraphDeduplicationRead(BaseModel):
    kb_id: int
    merged_relations: int
    deleted_duplicate_relations: int


class KnowledgeGraphDocumentRebuildRead(BaseModel):
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


class KnowledgeGraphExportEntityRead(BaseModel):
    id: int
    name: str
    entity_type: str | None = None
    mention_count: int
    relation_count: int


class KnowledgeGraphExportSourceRead(BaseModel):
    document_id: int | None = None
    filename: str | None = None
    chunk_id: int | None = None
    citation_unit_id: int | None = None
    snippet: str | None = None


class KnowledgeGraphExportRelationRead(BaseModel):
    id: int
    source_entity: str
    target_entity: str
    source_entity_id: int
    target_entity_id: int
    type: str
    label: str | None = None
    source_count: int
    sources: list[KnowledgeGraphExportSourceRead]


class KnowledgeGraphExportRead(BaseModel):
    kb_id: int
    entities: list[KnowledgeGraphExportEntityRead]
    relations: list[KnowledgeGraphExportRelationRead]
