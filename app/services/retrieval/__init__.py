from __future__ import annotations

from app.services.retrieval import chunk_retriever
from app.services.retrieval.chunk_retriever import (
    HybridCandidate,
    ProcessedRetrievalQuery,
    build_query_aware_chunk_snippet,
    merge_hybrid_candidates,
    preprocess_retrieval_query,
    score_lexical_text_match,
    score_metadata_match,
    search_document_chunks,
    search_document_chunks_lexical,
)
from app.services.retrieval.retrieval_router import (
    resolve_mode,
    resolve_retriever_name,
)
from app.services.retrieval.retrieval_service import retrieve
from app.services.retrieval.types import (
    RetrievedEvidence,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResult,
)

search_index = chunk_retriever.search_index


def retrieve_chunks_for_documents(*args, **kwargs):
    chunk_retriever.search_index = search_index
    return chunk_retriever.retrieve_chunks_for_documents(*args, **kwargs)

__all__ = [
    "HybridCandidate",
    "ProcessedRetrievalQuery",
    "RetrievedEvidence",
    "RetrievalMode",
    "RetrievalRequest",
    "RetrievalResult",
    "build_query_aware_chunk_snippet",
    "merge_hybrid_candidates",
    "preprocess_retrieval_query",
    "resolve_mode",
    "resolve_retriever_name",
    "retrieve",
    "retrieve_chunks_for_documents",
    "score_lexical_text_match",
    "score_metadata_match",
    "search_index",
    "search_document_chunks",
    "search_document_chunks_lexical",
]
