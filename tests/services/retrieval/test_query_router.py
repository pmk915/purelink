from __future__ import annotations

import pytest

from app.services.retrieval.query_router import route_query
from app.services.retrieval.types import RetrievalMode


@pytest.mark.parametrize(
    ("query", "expected_mode"),
    [
        ("总结一下这个知识库", RetrievalMode.OVERVIEW),
        ("DocumentBlock 和 chunk 是什么关系", RetrievalMode.GRAPH_VECTOR_MIX),
        ("CHUNK_STRATEGY 在哪里配置", RetrievalMode.HYBRID_TEXT),
        ("/api/kb/documents 接口在哪里", RetrievalMode.HYBRID_TEXT),
        ("这个文档说了什么结论", RetrievalMode.CHUNK_ONLY),
        ("What is the capital conclusion in this document?", RetrievalMode.CHUNK_ONLY),
        ("Give me an overview of the KB", RetrievalMode.OVERVIEW),
        ("Which services are connected to document ownership?", RetrievalMode.GRAPH_VECTOR_MIX),
        ("app/services/retrieval/retrieval_service.py 里的 function_name() 做什么", RetrievalMode.HYBRID_TEXT),
    ],
)
def test_route_query_selects_expected_mode(query: str, expected_mode: RetrievalMode) -> None:
    decision = route_query(query)

    assert decision.selected_mode == expected_mode
    assert decision.reason
