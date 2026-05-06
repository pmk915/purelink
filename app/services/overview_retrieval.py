from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.services.chunk_metadata import (
    build_chunk_snippet,
    infer_source_type_from_filename,
    parse_chunk_metadata,
)
from app.services.document_embedding import RetrievedChunk, tokenize_text


OVERVIEW_SECTION_KEYWORDS: tuple[str, ...] = (
    "摘要",
    "概述",
    "简介",
    "背景",
    "主要内容",
    "关键点",
    "总结",
    "结论",
    "引言",
    "abstract",
    "overview",
    "introduction",
    "summary",
    "conclusion",
    "background",
)

BOILERPLATE_KEYWORDS: tuple[str, ...] = (
    "目录",
    "免责声明",
    "版权",
    "页眉",
    "页脚",
    "参考文献",
    "附录",
    "table of contents",
    "copyright",
    "disclaimer",
    "references",
    "appendix",
)

LIST_MARKER_PATTERN = re.compile(
    r"(^|\n)\s*(?:[-*]\s+|\d+\.\s+|[一二三四五六七八九十]+、)",
    re.MULTILINE,
)
PUNCTUATION_STRIP_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
WHITESPACE_PATTERN = re.compile(r"\s+")

logger = logging.getLogger("purelink.qa")


@dataclass(frozen=True, slots=True)
class OverviewChunkCandidate:
    chunk: DocumentChunk
    document: Document
    score: float


def collect_overview_chunks(
    *,
    db: Session,
    documents: Sequence[Document],
    knowledge_base_id: int,
    scope: KnowledgeBaseScope,
    required_review_status: DocumentReviewStatus,
    team_id: int | None = None,
    max_chunks: int = 10,
    max_chunks_per_document: int = 2,
) -> list[RetrievedChunk]:
    indexed_documents = [
        item
        for item in documents
        if item.knowledge_base_id == knowledge_base_id
        and item.review_status == required_review_status
        and item.processing_status == DocumentProcessingStatus.INDEXED
    ]
    if not indexed_documents:
        return []

    document_lookup = {item.id: item for item in indexed_documents}
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id.in_(document_lookup.keys()))
        .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
    )
    chunks = list(db.scalars(statement))
    candidate_chunk_count = len(chunks)
    candidates_by_document: dict[int, list[OverviewChunkCandidate]] = defaultdict(list)

    for chunk in chunks:
        document = document_lookup.get(chunk.document_id)
        if document is None:
            continue
        candidates_by_document[chunk.document_id].append(
            OverviewChunkCandidate(
                chunk=chunk,
                document=document,
                score=overview_score_chunk(chunk, document_name=document.original_filename),
            )
        )

    per_document_candidates: dict[int, list[OverviewChunkCandidate]] = {}
    for document in indexed_documents:
        scored_chunks = sorted(
            candidates_by_document.get(document.id, []),
            key=lambda item: (-item.score, item.chunk.chunk_index, item.chunk.id),
        )
        selected_for_document: list[OverviewChunkCandidate] = []
        for candidate in scored_chunks:
            if len(selected_for_document) >= max_chunks_per_document:
                break
            if is_near_duplicate(
                candidate.chunk.chunk_text,
                [item.chunk.chunk_text for item in selected_for_document],
            ):
                continue
            selected_for_document.append(candidate)
        per_document_candidates[document.id] = selected_for_document

    final_candidates: list[OverviewChunkCandidate] = []
    for slot_index in range(max_chunks_per_document):
        for document in indexed_documents:
            candidates = per_document_candidates.get(document.id, [])
            if slot_index >= len(candidates):
                continue
            candidate = candidates[slot_index]
            if (
                slot_index > 0
                and is_near_duplicate(
                    candidate.chunk.chunk_text,
                    [item.chunk.chunk_text for item in final_candidates],
                )
            ):
                continue
            final_candidates.append(candidate)
            if len(final_candidates) >= max_chunks:
                break
        if len(final_candidates) >= max_chunks:
            break

    logger.info(
        "qa overview selection knowledge_base_id=%s indexed_document_count=%s candidate_chunk_count=%s selected_overview_chunk_count=%s selected_document_ids=%s selected_chunk_ids=%s overview_chunk_scores=%s",
        knowledge_base_id,
        len(indexed_documents),
        candidate_chunk_count,
        len(final_candidates),
        [item.document.id for item in final_candidates],
        [item.chunk.chunk_key for item in final_candidates],
        [round(item.score, 3) for item in final_candidates],
    )

    return [
        _build_retrieved_chunk_from_candidate(
            candidate,
            knowledge_base_id=knowledge_base_id,
            scope=scope,
            team_id=team_id,
        )
        for candidate in final_candidates
    ]


def overview_score_chunk(
    chunk: DocumentChunk,
    *,
    document_name: str | None = None,
) -> float:
    metadata = parse_chunk_metadata(
        chunk.metadata_json,
        fallback_source_type=(
            infer_source_type_from_filename(document_name)
            if document_name
            else None
        ),
    )
    section_title = _normalize_text(metadata.section_title or metadata.source_locator or "")
    normalized_text = _normalize_text(chunk.chunk_text)
    text_lower = normalized_text.lower()
    text_prefix = text_lower[:240]

    score = 0.0

    if any(keyword in section_title for keyword in OVERVIEW_SECTION_KEYWORDS):
        score += 3.0

    if any(keyword in text_prefix for keyword in OVERVIEW_SECTION_KEYWORDS):
        score += 1.0

    text_length = len(normalized_text)
    if 200 <= text_length <= 1200:
        score += 1.0
    elif 80 <= text_length < 200:
        score += 0.3
    elif text_length < 80:
        score -= 1.0

    if "：" in normalized_text or ":" in normalized_text:
        score += 0.5
    if LIST_MARKER_PATTERN.search(normalized_text):
        score += 0.5

    paragraphs = [line.strip() for line in chunk.chunk_text.splitlines() if line.strip()]
    if len(paragraphs) >= 3:
        score += 0.3

    score += max(0.0, 1.0 - (chunk.chunk_index * 0.1))

    if any(keyword in section_title or keyword in text_prefix for keyword in BOILERPLATE_KEYWORDS):
        score -= 2.0

    return score


def is_near_duplicate(
    text: str,
    selected_texts: Sequence[str],
    *,
    threshold: float = 0.75,
) -> bool:
    if not selected_texts:
        return False

    candidate = _normalize_dedup_text(text)
    if not candidate:
        return False

    candidate_grams = _build_character_bigrams(candidate)
    for item in selected_texts:
        existing = _normalize_dedup_text(item)
        if not existing:
            continue
        if candidate == existing:
            return True
        if candidate in existing or existing in candidate:
            shorter = candidate if len(candidate) <= len(existing) else existing
            longer = existing if shorter == candidate else candidate
            if shorter and (len(shorter) / max(1, len(longer))) >= 0.55:
                return True
        existing_grams = _build_character_bigrams(existing)
        if not candidate_grams or not existing_grams:
            continue
        intersection = candidate_grams & existing_grams
        overlap = len(intersection) / max(
            1,
            len(candidate_grams | existing_grams),
        )
        smaller_gram_coverage = len(intersection) / max(
            1,
            min(len(candidate_grams), len(existing_grams)),
        )
        if overlap >= threshold or smaller_gram_coverage >= threshold:
            return True
    return False


def _build_retrieved_chunk_from_candidate(
    candidate: OverviewChunkCandidate,
    *,
    knowledge_base_id: int,
    scope: KnowledgeBaseScope,
    team_id: int | None,
) -> RetrievedChunk:
    metadata = parse_chunk_metadata(
        candidate.chunk.metadata_json,
        fallback_source_type=infer_source_type_from_filename(candidate.document.original_filename),
    )
    return RetrievedChunk(
        chunk_db_id=candidate.chunk.id,
        chunk_id=candidate.chunk.chunk_key,
        document_id=candidate.document.id,
        knowledge_base_id=knowledge_base_id,
        scope=scope.value,
        team_id=team_id,
        document_name=candidate.document.original_filename,
        text=candidate.chunk.chunk_text,
        snippet=build_chunk_snippet(candidate.chunk.chunk_text),
        source_type=metadata.source_type,
        char_start=metadata.char_start,
        char_end=metadata.char_end,
        page_number=metadata.page_number,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        section_title=metadata.section_title,
        source_locator=metadata.source_locator,
        heading_path=metadata.heading_path,
        score=max(0.0, candidate.score),
        ocr_provider=metadata.ocr_provider,
        ocr_provider_version=metadata.ocr_provider_version,
        asr_provider=metadata.asr_provider,
        asr_provider_version=metadata.asr_provider_version,
    )


def _normalize_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip().lower()


def _normalize_dedup_text(text: str) -> str:
    normalized = _normalize_text(text)
    compact = PUNCTUATION_STRIP_PATTERN.sub("", normalized)
    return compact[:320]


def _build_character_bigrams(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}
