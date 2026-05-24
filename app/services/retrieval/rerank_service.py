from __future__ import annotations

from app.core.config import Settings
from app.providers.reranker import (
    NoopRerankerProvider,
    RerankCandidate,
    get_reranker_provider,
)
from app.providers.reranker.base import RerankerProviderError
from app.services.document_embedding import RetrievedChunk
from app.services.retrieval.types import RetrievedEvidence


def should_expand_initial_recall(settings: Settings) -> bool:
    return bool(settings.reranker_enabled and settings.reranker_provider != "noop")


async def rerank_evidences(
    *,
    query: str,
    evidences: list[RetrievedEvidence],
    top_k: int,
    settings: Settings,
) -> tuple[list[RetrievedEvidence], bool]:
    if top_k <= 0:
        return [], False
    if not evidences:
        return [], False
    if not should_expand_initial_recall(settings):
        return evidences[:top_k], False

    provider = get_reranker_provider(settings)
    if isinstance(provider, NoopRerankerProvider):
        return evidences[:top_k], False

    candidates = [
        RerankCandidate(
            id=_build_candidate_id(evidence),
            text=evidence.text,
            metadata=_build_candidate_metadata(evidence),
        )
        for evidence in evidences
    ]
    results = await provider.rerank(query=query, candidates=candidates, top_n=top_k)
    evidence_by_id = {
        _build_candidate_id(evidence): evidence
        for evidence in evidences
    }

    reranked: list[RetrievedEvidence] = []
    seen_ids: set[str] = set()
    for result in sorted(results, key=lambda item: item.rank):
        evidence = evidence_by_id.get(result.id)
        if evidence is None or result.id in seen_ids:
            continue
        seen_ids.add(result.id)
        reranked.append(
            evidence.model_copy(
                update={
                    "rerank_score": result.score,
                    "final_score": result.score,
                }
            )
        )
        if len(reranked) >= top_k:
            break

    return reranked, bool(reranked)


def align_chunks_to_evidences(
    *,
    chunks: list[RetrievedChunk],
    evidences: list[RetrievedEvidence],
) -> list[RetrievedChunk]:
    chunks_by_key = {
        (chunk.document_id, str(chunk.chunk_id)): chunk
        for chunk in chunks
    }
    aligned: list[RetrievedChunk] = []
    for evidence in evidences:
        chunk = chunks_by_key.get((evidence.document_id, str(evidence.chunk_id)))
        if chunk is None:
            continue
        aligned.append(chunk)
    return aligned


def _build_candidate_id(evidence: RetrievedEvidence) -> str:
    if evidence.citation_unit_id is not None:
        return f"citation_unit:{evidence.citation_unit_id}"
    if evidence.chunk_db_id is not None:
        return f"chunk_db:{evidence.chunk_db_id}"
    return f"chunk:{evidence.document_id}:{evidence.chunk_id}"


def _build_candidate_metadata(evidence: RetrievedEvidence) -> dict[str, object]:
    return {
        "document_id": evidence.document_id,
        "document_name": evidence.document_name,
        "chunk_id": evidence.chunk_id,
        "citation_unit_id": evidence.citation_unit_id,
        "source_locator": evidence.source_locator,
        "section_title": evidence.section_title,
    }


__all__ = [
    "RerankerProviderError",
    "align_chunks_to_evidences",
    "rerank_evidences",
    "should_expand_initial_recall",
]
