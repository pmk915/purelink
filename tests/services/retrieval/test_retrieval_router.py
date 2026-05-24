from __future__ import annotations

from app.services.retrieval.retrieval_router import (
    resolve_mode,
    resolve_retriever_name,
)
from app.services.retrieval.types import RetrievalMode


def test_chunk_only_routes_to_chunk_retriever() -> None:
    assert resolve_mode(RetrievalMode.CHUNK_ONLY) == RetrievalMode.CHUNK_ONLY
    assert resolve_retriever_name(RetrievalMode.CHUNK_ONLY) == "chunk"


def test_overview_routes_to_overview_adapter() -> None:
    assert resolve_mode(RetrievalMode.OVERVIEW) == RetrievalMode.OVERVIEW
    assert resolve_retriever_name(RetrievalMode.OVERVIEW) == "overview"


def test_future_graph_modes_fallback_to_chunk_only() -> None:
    assert resolve_mode(RetrievalMode.GRAPH_LOCAL) == RetrievalMode.CHUNK_ONLY
    assert resolve_mode(RetrievalMode.GRAPH_GLOBAL) == RetrievalMode.CHUNK_ONLY


def test_graph_vector_mix_routes_to_graph_retriever() -> None:
    assert resolve_mode(RetrievalMode.GRAPH_VECTOR_MIX) == RetrievalMode.GRAPH_VECTOR_MIX
    assert resolve_retriever_name(RetrievalMode.GRAPH_VECTOR_MIX) == "graph_vector_mix"
