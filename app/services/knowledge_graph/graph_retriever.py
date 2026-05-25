from __future__ import annotations

from dataclasses import replace

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_graph import EntityMention, KnowledgeEntity, KnowledgeRelation
from app.services.chunk_metadata import build_chunk_snippet, infer_source_type_from_filename, parse_chunk_metadata
from app.services.document_embedding import RetrievedChunk
from app.services.knowledge_graph.graph_extractor import extract_query_entities
from app.services.knowledge_graph.normalizer import normalize_entity_name


def retrieve_graph_chunks(
    *,
    db: Session,
    documents: list[Document],
    knowledge_base_id: int,
    query: str,
    scope: str,
    team_id: int | None,
    limit: int,
) -> list[RetrievedChunk]:
    if limit <= 0 or not documents:
        return []

    allowed_document_ids = {document.id for document in documents}
    matched_entities = _match_query_entities(
        db,
        knowledge_base_id=knowledge_base_id,
        query=query,
    )
    if not matched_entities:
        return []

    matched_entity_ids = {item.id for item in matched_entities}
    candidate_scores: dict[int, float] = {}

    for mention in db.scalars(
        select(EntityMention).where(
            EntityMention.knowledge_base_id == knowledge_base_id,
            EntityMention.entity_id.in_(matched_entity_ids),
            EntityMention.document_id.in_(allowed_document_ids),
            EntityMention.chunk_id.is_not(None),
        )
    ):
        if mention.chunk_id is not None:
            candidate_scores[mention.chunk_id] = max(candidate_scores.get(mention.chunk_id, 0.0), 1.0)

    relation_statement = select(KnowledgeRelation).where(
        KnowledgeRelation.knowledge_base_id == knowledge_base_id,
        KnowledgeRelation.source_document_id.in_(allowed_document_ids),
        KnowledgeRelation.source_chunk_id.is_not(None),
        or_(
            KnowledgeRelation.source_entity_id.in_(matched_entity_ids),
            KnowledgeRelation.target_entity_id.in_(matched_entity_ids),
        ),
    )
    normalized_query = query.casefold()
    for relation in db.scalars(relation_statement):
        if relation.source_chunk_id is None:
            continue
        score = 0.7
        if relation.relation_type.casefold() in normalized_query:
            score += 0.1
        if relation.confidence is not None:
            score += min(relation.confidence, 1.0) * 0.1
        candidate_scores[relation.source_chunk_id] = max(
            candidate_scores.get(relation.source_chunk_id, 0.0),
            min(score, 1.0),
        )

    if not candidate_scores:
        return []

    chunks = {
        chunk.id: chunk
        for chunk in db.scalars(
            select(DocumentChunk).where(DocumentChunk.id.in_(candidate_scores.keys()))
        )
    }
    document_lookup = {document.id: document for document in documents}
    results = [
        _build_retrieved_chunk(
            chunk,
            document_lookup=document_lookup,
            knowledge_base_id=knowledge_base_id,
            scope=scope,
            team_id=team_id,
            score=score,
        )
        for chunk_id, score in candidate_scores.items()
        if (chunk := chunks.get(chunk_id)) is not None
    ]
    results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return results[:limit]


def _match_query_entities(
    db: Session,
    *,
    knowledge_base_id: int,
    query: str,
) -> list[KnowledgeEntity]:
    extracted_names = set(extract_query_entities(query))
    normalized_query = normalize_entity_name(query)
    entities = list(
        db.scalars(
            select(KnowledgeEntity).where(KnowledgeEntity.knowledge_base_id == knowledge_base_id)
        )
    )
    matched = []
    for entity in entities:
        if entity.normalized_name in extracted_names:
            matched.append(entity)
            continue
        if entity.normalized_name and entity.normalized_name in normalized_query:
            matched.append(entity)
    return matched


def _build_retrieved_chunk(
    chunk: DocumentChunk,
    *,
    document_lookup: dict[int, Document],
    knowledge_base_id: int,
    scope: str,
    team_id: int | None,
    score: float,
) -> RetrievedChunk:
    document = document_lookup.get(chunk.document_id)
    document_name = (
        document.original_filename
        if document is not None
        else f"document_{chunk.document_id}"
    )
    metadata = parse_chunk_metadata(
        chunk.metadata_json,
        fallback_source_type=infer_source_type_from_filename(document_name),
    )
    snippet = build_chunk_snippet(chunk.chunk_text)
    return RetrievedChunk(
        chunk_db_id=chunk.id,
        chunk_id=chunk.chunk_key,
        document_id=chunk.document_id,
        knowledge_base_id=knowledge_base_id,
        scope=scope,
        team_id=team_id,
        document_name=document_name,
        text=chunk.chunk_text,
        snippet=snippet,
        source_type=metadata.source_type,
        char_start=metadata.char_start,
        char_end=metadata.char_end,
        page_number=metadata.page_number,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        section_title=metadata.section_title,
        source_locator=metadata.source_locator,
        heading_path=metadata.heading_path,
        score=score,
        graph_score=score,
        candidate_sources=("graph",),
    )


def merge_graph_and_vector_chunks(
    *,
    vector_chunks: list[RetrievedChunk],
    graph_chunks: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    merged: dict[tuple[int, str], RetrievedChunk] = {
        (chunk.document_id, str(chunk.chunk_id)): chunk
        for chunk in vector_chunks
    }
    for graph_chunk in graph_chunks:
        key = (graph_chunk.document_id, str(graph_chunk.chunk_id))
        existing = merged.get(key)
        if existing is None:
            merged[key] = graph_chunk
            continue
        merged[key] = replace(existing, score=max(existing.score, graph_chunk.score))
    results = list(merged.values())
    results.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id))
    return results[:top_k]
