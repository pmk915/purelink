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
