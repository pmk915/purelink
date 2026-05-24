from __future__ import annotations

import logging

from app.services.retrieval.types import RetrievalMode


logger = logging.getLogger("purelink.retrieval")

SUPPORTED_MODES = {
    RetrievalMode.CHUNK_ONLY,
    RetrievalMode.OVERVIEW,
    RetrievalMode.GRAPH_VECTOR_MIX,
}


def resolve_mode(requested_mode: RetrievalMode) -> RetrievalMode:
    if requested_mode in SUPPORTED_MODES:
        return requested_mode

    logger.info(
        "retrieval mode fallback requested_mode=%s fallback_mode=%s",
        requested_mode.value,
        RetrievalMode.CHUNK_ONLY.value,
    )
    return RetrievalMode.CHUNK_ONLY


def resolve_retriever_name(requested_mode: RetrievalMode) -> str:
    resolved_mode = resolve_mode(requested_mode)
    if resolved_mode == RetrievalMode.OVERVIEW:
        return "overview"
    if resolved_mode == RetrievalMode.GRAPH_VECTOR_MIX:
        return "graph_vector_mix"
    return "chunk"
