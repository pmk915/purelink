from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedEntity(BaseModel):
    name: str
    normalized_name: str
    entity_type: str | None = None
    description: str | None = None
    confidence: float | None = None


class ExtractedRelation(BaseModel):
    source_name: str
    target_name: str
    relation_type: str
    description: str | None = None
    confidence: float | None = None
    source_document_id: int | None = None
    source_chunk_id: int | None = None
    source_citation_unit_id: int | None = None


class ExtractedMention(BaseModel):
    entity_name: str
    normalized_name: str
    source_document_id: int
    source_chunk_id: int | None = None
    source_citation_unit_id: int | None = None
    text_span: str | None = None
    source_locator: str | None = None


class GraphExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
    mentions: list[ExtractedMention] = Field(default_factory=list)


class GraphSourceText(BaseModel):
    document_id: int
    chunk_id: int | None = None
    citation_unit_id: int | None = None
    text: str
    source_locator: str | None = None
