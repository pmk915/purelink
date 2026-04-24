from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
import re
from typing import Protocol

from app.core.config import Settings, get_settings
from app.services.document_embedding import RetrievedChunk, tokenize_text


LOCAL_RULE_RERANKER = "local_rule_reranker"
EXTERNAL_RERANK_API = "external_rerank_api"
CROSS_ENCODER_RERANKER = "cross_encoder_reranker"
LLM_RERANKER = "llm_rerank"
WHITESPACE_PATTERN = re.compile(r"\s+")
RERANK_RANGE_OVERLAP_THRESHOLD = 0.55
RERANK_TOKEN_JACCARD_THRESHOLD = 0.82


class RerankerError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    chunk: RetrievedChunk
    hybrid_score: float
    query_coverage_score: float
    metadata_match_score: float
    section_match_score: float
    rerank_score: float


class Reranker(Protocol):
    provider_name: str

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RerankCandidate]: ...


@dataclass(frozen=True, slots=True)
class LocalRuleReranker:
    provider_name: str = LOCAL_RULE_RERANKER

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RerankCandidate]:
        if top_k <= 0 or not candidates:
            return []

        normalized_query = WHITESPACE_PATTERN.sub(" ", query.strip()).lower()
        query_tokens = tuple(tokenize_text(normalized_query))
        if not query_tokens:
            return [
                RerankCandidate(
                    chunk=item,
                    hybrid_score=item.score,
                    query_coverage_score=0.0,
                    metadata_match_score=0.0,
                    section_match_score=0.0,
                    rerank_score=item.score,
                )
                for item in candidates[:top_k]
            ]

        prepared = [
            _prepare_rerank_candidate(
                query=query,
                normalized_query=normalized_query,
                query_tokens=query_tokens,
                chunk=item,
            )
            for item in candidates
        ]

        selected: list[RerankCandidate] = []
        remaining = prepared[:]
        per_document_count: dict[int, int] = defaultdict(int)

        while remaining and len(selected) < top_k:
            best_index = 0
            best_candidate = _apply_selection_penalties(
                remaining[0],
                selected=selected,
                per_document_count=per_document_count,
            )

            for index, candidate in enumerate(remaining[1:], start=1):
                adjusted = _apply_selection_penalties(
                    candidate,
                    selected=selected,
                    per_document_count=per_document_count,
                )
                if adjusted.rerank_score > best_candidate.rerank_score:
                    best_index = index
                    best_candidate = adjusted

            selected.append(best_candidate)
            per_document_count[best_candidate.chunk.document_id] += 1
            remaining.pop(best_index)

        return selected


def rerank_candidates(
    *,
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    if top_k <= 0 or not candidates:
        return []

    active_settings = settings or get_settings()
    if not active_settings.reranker_enabled:
        return candidates[:top_k]

    try:
        reranker = resolve_reranker(active_settings)
        reranked = reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=top_k,
        )
    except RerankerError:
        return candidates[:top_k]

    return [
        replace(candidate.chunk, score=min(1.0, max(0.0, candidate.rerank_score)))
        for candidate in reranked
    ]


def resolve_reranker(settings: Settings | None = None) -> Reranker:
    active_settings = settings or get_settings()
    provider = active_settings.reranker_provider.strip().lower()
    if provider == LOCAL_RULE_RERANKER:
        return LocalRuleReranker()
    if provider in {
        EXTERNAL_RERANK_API,
        CROSS_ENCODER_RERANKER,
        LLM_RERANKER,
    }:
        raise RerankerError(f"Unsupported reranker provider: {provider}.")
    raise RerankerError(f"Unknown reranker provider: {provider}.")


def _prepare_rerank_candidate(
    *,
    query: str,
    normalized_query: str,
    query_tokens: tuple[str, ...],
    chunk: RetrievedChunk,
) -> RerankCandidate:
    coverage_score = _score_query_coverage(query_tokens=query_tokens, text=chunk.text)
    metadata_score = _score_metadata_quality(query_tokens=query_tokens, chunk=chunk)
    section_score = _score_section_match(
        query=query,
        normalized_query=normalized_query,
        chunk=chunk,
    )
    rerank_score = min(
        1.0,
        (0.60 * chunk.score)
        + (0.20 * coverage_score)
        + (0.12 * metadata_score)
        + (0.08 * section_score),
    )
    return RerankCandidate(
        chunk=chunk,
        hybrid_score=chunk.score,
        query_coverage_score=coverage_score,
        metadata_match_score=metadata_score,
        section_match_score=section_score,
        rerank_score=rerank_score,
    )


def _apply_selection_penalties(
    candidate: RerankCandidate,
    *,
    selected: list[RerankCandidate],
    per_document_count: dict[int, int],
) -> RerankCandidate:
    penalty = min(0.22, 0.07 * per_document_count[candidate.chunk.document_id])
    for existing in selected:
        if existing.chunk.document_id != candidate.chunk.document_id:
            continue
        if _chunks_heavily_overlap(candidate.chunk, existing.chunk):
            penalty += 0.18
        if _same_source_locator(candidate.chunk, existing.chunk):
            penalty += 0.08

    adjusted_score = max(0.0, candidate.rerank_score - penalty)
    return RerankCandidate(
        chunk=candidate.chunk,
        hybrid_score=candidate.hybrid_score,
        query_coverage_score=candidate.query_coverage_score,
        metadata_match_score=candidate.metadata_match_score,
        section_match_score=candidate.section_match_score,
        rerank_score=adjusted_score,
    )


def _score_query_coverage(*, query_tokens: tuple[str, ...], text: str) -> float:
    chunk_tokens = tuple(tokenize_text(text))
    if not chunk_tokens:
        return 0.0

    query_unique = set(query_tokens)
    chunk_unique = set(chunk_tokens)
    coverage = len(query_unique & chunk_unique) / max(len(query_unique), 1)
    density = len(query_unique & chunk_unique) / max(min(len(chunk_unique), 200), 1)
    return min(1.0, (0.8 * coverage) + (0.2 * min(density * 8, 1.0)))


def _score_metadata_quality(*, query_tokens: tuple[str, ...], chunk: RetrievedChunk) -> float:
    metadata_parts: list[str] = []
    if chunk.section_title:
        metadata_parts.append(chunk.section_title)
    if chunk.heading_path:
        metadata_parts.extend(chunk.heading_path)
    if chunk.source_locator:
        metadata_parts.append(chunk.source_locator)
    if chunk.page_number is not None:
        metadata_parts.append(f"page {chunk.page_number}")
    if chunk.source_type:
        metadata_parts.append(chunk.source_type)

    metadata_tokens = set(tokenize_text(" ".join(metadata_parts)))
    if not metadata_tokens:
        return 0.0

    query_unique = set(query_tokens)
    return len(query_unique & metadata_tokens) / max(len(query_unique), 1)


def _score_section_match(
    *,
    query: str,
    normalized_query: str,
    chunk: RetrievedChunk,
) -> float:
    section_text = " ".join(
        part
        for part in [
            chunk.section_title,
            *(chunk.heading_path or ()),
        ]
        if part
    )
    if not section_text:
        return 0.0

    normalized_section = WHITESPACE_PATTERN.sub(" ", section_text.strip()).lower()
    if not normalized_section:
        return 0.0
    if normalized_query and normalized_query in normalized_section:
        return 1.0

    query_tokens = set(tokenize_text(query))
    section_tokens = set(tokenize_text(section_text))
    if not query_tokens or not section_tokens:
        return 0.0
    return len(query_tokens & section_tokens) / max(len(query_tokens), 1)


def _chunks_heavily_overlap(left: RetrievedChunk, right: RetrievedChunk) -> bool:
    if (
        left.char_start is not None
        and left.char_end is not None
        and right.char_start is not None
        and right.char_end is not None
    ):
        left_start, left_end = sorted((left.char_start, left.char_end))
        right_start, right_end = sorted((right.char_start, right.char_end))
        overlap_start = max(left_start, right_start)
        overlap_end = min(left_end, right_end)
        if overlap_end > overlap_start:
            overlap_width = overlap_end - overlap_start
            smaller_width = max(1, min(left_end - left_start, right_end - right_start))
            if (overlap_width / smaller_width) >= RERANK_RANGE_OVERLAP_THRESHOLD:
                return True

    left_tokens = set(tokenize_text(left.text))
    right_tokens = set(tokenize_text(right.text))
    if not left_tokens or not right_tokens:
        return False
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return False
    return (intersection / union) >= RERANK_TOKEN_JACCARD_THRESHOLD


def _same_source_locator(left: RetrievedChunk, right: RetrievedChunk) -> bool:
    if left.source_locator and right.source_locator:
        return left.source_locator == right.source_locator
    return left.section_title is not None and left.section_title == right.section_title
