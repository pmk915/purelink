from __future__ import annotations

import pytest

from app.services.retrieval.query_router import CONFIDENCE_HIGH, CONFIDENCE_LOW, route_query
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
        ("Which service depends on DocumentBlock?", RetrievalMode.GRAPH_VECTOR_MIX),
        ("app/services/retrieval/retrieval_service.py 里的 function_name() 做什么", RetrievalMode.HYBRID_TEXT),
        ("这个文档主要包含哪些内容？", RetrievalMode.OVERVIEW),
        ("介绍一下 PostgreSQL MVCC", RetrievalMode.CHUNK_ONLY),
        ("FastAPI dependency 是什么？", RetrievalMode.CHUNK_ONLY),
        ("Alice Chen 和 Bob Li 是什么关系？", RetrievalMode.GRAPH_VECTOR_MIX),
        ("Aurora Labs 属于哪个组织？", RetrievalMode.GRAPH_VECTOR_MIX),
        ("Alice Chen 在哪里办公？", RetrievalMode.CHUNK_ONLY),
        ("成员有哪些特点？", RetrievalMode.CHUNK_ONLY),
        ("权限有什么作用？", RetrievalMode.CHUNK_ONLY),
        ("RETRIEVAL_MIN_SCORE 默认值是什么？", RetrievalMode.HYBRID_TEXT),
        ("docker compose down -v 有什么影响？", RetrievalMode.HYBRID_TEXT),
        ("__init__ 在什么时候调用？", RetrievalMode.HYBRID_TEXT),
        ("/api/v1/documents 返回什么？", RetrievalMode.HYBRID_TEXT),
        ("PostgreSQL 为什么使用 MVCC？", RetrievalMode.CHUNK_ONLY),
        ("Python 类是什么？", RetrievalMode.CHUNK_ONLY),
        ("block_aware 有什么特点？", RetrievalMode.CHUNK_ONLY),
        ("citation source locator 能保存什么信息？", RetrievalMode.HYBRID_TEXT),
        ("PostgreSQL 并发控制主要包含什么？", RetrievalMode.OVERVIEW),
        ("PureLink retrieval 有哪些主要组件？", RetrievalMode.OVERVIEW),
        ("当前语料中的团队成员有哪些？", RetrievalMode.OVERVIEW),
    ],
)
def test_route_query_selects_expected_mode(query: str, expected_mode: RetrievalMode) -> None:
    decision = route_query(query)

    assert decision.selected_mode == expected_mode
    assert decision.reason


@pytest.mark.parametrize(
    "query",
    [
        "总结 Python classes 文档",
        "Alice Chen 和 Bob Li 是什么关系？",
        "RETRIEVAL_MIN_SCORE 默认值是什么？",
    ],
)
def test_route_query_high_confidence_for_clear_signals(query: str) -> None:
    assert route_query(query).confidence == CONFIDENCE_HIGH


@pytest.mark.parametrize(
    "query",
    [
        "成员有哪些特点？",
        "权限有什么作用？",
        "FastAPI dependency 是什么？",
    ],
)
def test_route_query_low_confidence_defaults_to_chunk_only(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.CHUNK_ONLY
    assert decision.confidence == CONFIDENCE_LOW
