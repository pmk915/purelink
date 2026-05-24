from __future__ import annotations

from itertools import combinations
import re

from app.services.knowledge_graph.normalizer import canonical_entity_name, normalize_entity_name
from app.services.knowledge_graph.types import (
    ExtractedEntity,
    ExtractedMention,
    ExtractedRelation,
    GraphExtractionResult,
    GraphSourceText,
)


TECHNICAL_TERMS: tuple[tuple[str, str], ...] = (
    ("用户", "role"),
    ("团队", "domain"),
    ("知识库", "domain"),
    ("管理员", "role"),
    ("普通成员", "role"),
    ("成员", "role"),
    ("文档", "document"),
    ("文件", "document"),
    ("审核", "workflow"),
    ("删除", "action"),
    ("上传", "action"),
    ("索引", "index"),
    ("检索", "retrieval"),
    ("引用", "citation"),
    ("chunk", "retrieval"),
    ("embedding", "model"),
    ("reranker", "model"),
    ("citation", "citation"),
    ("worker", "component"),
    ("Redis", "component"),
    ("PostgreSQL", "component"),
    ("FastAPI", "component"),
    ("GraphRAG", "retrieval"),
    ("LightRAG", "retrieval"),
    ("PureLink", "product"),
)
CAPITALIZED_TERM_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9_+-]{2,}\b")


def extract_graph_from_sources(sources: list[GraphSourceText]) -> GraphExtractionResult:
    entity_by_normalized: dict[str, ExtractedEntity] = {}
    mentions: list[ExtractedMention] = []
    relations: list[ExtractedRelation] = []
    seen_mentions: set[tuple[str, int, int | None, int | None]] = set()
    seen_relations: set[tuple[str, str, str, int | None, int | None]] = set()

    for source in sources:
        source_entities = _extract_entities_from_text(source.text)
        for entity in source_entities:
            entity_by_normalized.setdefault(entity.normalized_name, entity)
            mention_key = (
                entity.normalized_name,
                source.document_id,
                source.chunk_id,
                source.citation_unit_id,
            )
            if mention_key not in seen_mentions:
                seen_mentions.add(mention_key)
                mentions.append(
                    ExtractedMention(
                        entity_name=entity.name,
                        normalized_name=entity.normalized_name,
                        source_document_id=source.document_id,
                        source_chunk_id=source.chunk_id,
                        source_citation_unit_id=source.citation_unit_id,
                        text_span=entity.name,
                        source_locator=source.source_locator,
                    )
                )

        for relation in _extract_relations_from_text(source.text, source_entities, source):
            relation_key = (
                normalize_entity_name(relation.source_name),
                normalize_entity_name(relation.target_name),
                relation.relation_type,
                relation.source_chunk_id,
                relation.source_citation_unit_id,
            )
            if relation_key in seen_relations:
                continue
            seen_relations.add(relation_key)
            relations.append(relation)

    return GraphExtractionResult(
        entities=sorted(entity_by_normalized.values(), key=lambda item: item.normalized_name),
        relations=relations,
        mentions=mentions,
    )


def extract_query_entities(query: str) -> list[str]:
    return [
        entity.normalized_name
        for entity in _extract_entities_from_text(query)
    ]


def _extract_entities_from_text(text: str) -> list[ExtractedEntity]:
    entities: dict[str, ExtractedEntity] = {}
    normalized_text = text.casefold()

    for term, entity_type in TECHNICAL_TERMS:
        if normalize_entity_name(term) in normalized_text:
            _add_entity(entities, name=term, entity_type=entity_type, confidence=0.9)

    for match in CAPITALIZED_TERM_PATTERN.finditer(text):
        value = canonical_entity_name(match.group(0))
        if value.lower() in {"the", "and", "for", "with"}:
            continue
        _add_entity(entities, name=value, entity_type="technical_term", confidence=0.6)

    return list(entities.values())


def _extract_relations_from_text(
    text: str,
    entities: list[ExtractedEntity],
    source: GraphSourceText,
) -> list[ExtractedRelation]:
    relations: list[ExtractedRelation] = []
    normalized_text = text.casefold()

    def add(source_name: str, target_name: str, relation_type: str, confidence: float = 0.8) -> None:
        relations.append(
            ExtractedRelation(
                source_name=source_name,
                target_name=target_name,
                relation_type=relation_type,
                confidence=confidence,
                source_document_id=source.document_id,
                source_chunk_id=source.chunk_id,
                source_citation_unit_id=source.citation_unit_id,
            )
        )

    if "管理员" in text and "删除" in text and ("文档" in text or "文件" in text):
        add("管理员", "文档" if "文档" in text else "文件", "can_delete", confidence=0.95)
    if ("普通成员" in text or "成员" in text) and "上传" in text and ("文档" in text or "文件" in text):
        add("普通成员" if "普通成员" in text else "成员", "文档" if "文档" in text else "文件", "can_upload", confidence=0.9)
    if "pending_review" in normalized_text or "待审核" in text:
        add("文档", "pending_review", "has_status", confidence=0.8)
    if "indexed" in normalized_text or "已索引" in text:
        add("文档", "indexed", "has_status", confidence=0.8)

    cooccurring = [item.name for item in entities[:5]]
    for left, right in combinations(cooccurring, 2):
        add(left, right, "co_occurs_with", confidence=0.45)
    return relations


def _add_entity(
    entities: dict[str, ExtractedEntity],
    *,
    name: str,
    entity_type: str,
    confidence: float,
) -> None:
    canonical = canonical_entity_name(name)
    if not canonical:
        return
    normalized = normalize_entity_name(canonical)
    existing = entities.get(normalized)
    if existing is None or (existing.confidence or 0.0) < confidence:
        entities[normalized] = ExtractedEntity(
            name=canonical,
            normalized_name=normalized,
            entity_type=entity_type,
            confidence=confidence,
        )
