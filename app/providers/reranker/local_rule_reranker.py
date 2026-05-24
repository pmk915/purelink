from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import re

from app.providers.reranker.base import (
    RerankCandidate,
    RerankResult,
    RerankerProviderInfo,
)


LOCAL_RULE_RERANKER_PROVIDER = "local_rule_reranker"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
WHITESPACE_PATTERN = re.compile(r"\s+")


class LocalRuleRerankerProvider:
    provider_name = LOCAL_RULE_RERANKER_PROVIDER
    model_name = LOCAL_RULE_RERANKER_PROVIDER

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_n: int,
    ) -> list[RerankResult]:
        if top_n <= 0 or not candidates:
            return []

        normalized_query = _normalize_text(query)
        query_terms = tuple(_tokenize(normalized_query))
        if not query_terms:
            return [
                RerankResult(
                    id=candidate.id,
                    score=0.0,
                    rank=index + 1,
                    metadata=candidate.metadata,
                )
                for index, candidate in enumerate(candidates[:top_n])
            ]

        query_counts = Counter(query_terms)
        scored = [
            (
                _score_candidate(
                    normalized_query=normalized_query,
                    query_counts=query_counts,
                    candidate=candidate,
                ),
                index,
                candidate,
            )
            for index, candidate in enumerate(candidates)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))

        return [
            RerankResult(
                id=candidate.id,
                score=score,
                rank=rank,
                metadata=candidate.metadata,
            )
            for rank, (score, _, candidate) in enumerate(scored[:top_n], start=1)
        ]

    async def get_info(self) -> RerankerProviderInfo:
        return RerankerProviderInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            enabled=True,
            available=True,
        )


def _score_candidate(
    *,
    normalized_query: str,
    query_counts: Counter[str],
    candidate: RerankCandidate,
) -> float:
    text = _normalize_text(candidate.text)
    if not text:
        return 0.0

    text_counts = Counter(_tokenize(text))
    matched_terms = {
        token for token in query_counts if text_counts.get(token, 0) > 0
    }
    overlap = len(matched_terms) / max(len(query_counts), 1)
    term_hits = sum(
        min(query_count, text_counts.get(token, 0))
        for token, query_count in query_counts.items()
    )
    recall = term_hits / max(sum(query_counts.values()), 1)
    exact_match = 0.35 if normalized_query and normalized_query in text else 0.0

    metadata_text = _normalize_text(
        " ".join(
            str(value)
            for value in [
                candidate.metadata.get("document_name"),
                candidate.metadata.get("source_locator"),
                candidate.metadata.get("section_title"),
            ]
            if value
        )
    )
    metadata_tokens = set(_tokenize(metadata_text))
    metadata_hit = (
        len(set(query_counts) & metadata_tokens) / max(len(query_counts), 1)
        if metadata_tokens
        else 0.0
    )

    return min(1.0, exact_match + (0.45 * overlap) + (0.15 * recall) + (0.05 * metadata_hit))


def _normalize_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text.strip()).lower()


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)
