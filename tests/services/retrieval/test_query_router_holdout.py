from __future__ import annotations

import pytest

from app.services.retrieval.query_router import CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MANUAL, route_query
from app.services.retrieval.retrieval_service import _select_retrieval_mode
from app.services.retrieval.types import RetrievalMode, RetrievalRequest


@pytest.mark.parametrize(
    "query",
    [
        "把 Python classes 这份文档的核心内容归纳一下。",
        "这份员工政策一共讲了哪些方面？",
        "Give me an overview of PostgreSQL concurrency control.",
        "请列出 PureLink 文档处理流程的主要环节。",
    ],
)
def test_overview_holdout_routes_clear_summary_requests_to_overview(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.OVERVIEW
    assert decision.confidence == CONFIDENCE_HIGH


@pytest.mark.parametrize(
    "query",
    [
        "介绍一下 MVCC 的作用。",
        "FastAPI dependency 有哪些特点？",
        "DocumentBlock 是什么？",
    ],
)
def test_overview_holdout_does_not_route_specific_concepts_to_overview(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.CHUNK_ONLY


@pytest.mark.parametrize(
    "query",
    [
        "Alice Chen 隶属于哪个团队？",
        "Bob Li 与 Alice Chen 如何协作？",
        "What is the relationship between a class and an instance?",
        "citation unit 和 chunk 之间是什么从属关系？",
    ],
)
def test_relation_holdout_routes_explicit_relationship_questions_to_graph(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.GRAPH_VECTOR_MIX
    assert decision.confidence == CONFIDENCE_HIGH


@pytest.mark.parametrize(
    "query",
    [
        "权限控制有什么作用？",
        "dependency injection 是什么？",
        "Python 的成员变量是什么？",
        "团队成员有哪些特点？",
    ],
)
def test_relation_holdout_does_not_route_weak_relation_terms_to_graph(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.CHUNK_ONLY


@pytest.mark.parametrize(
    "query",
    [
        "环境变量 RETRIEVAL_MIN_SCORE 的默认值是多少？",
        "执行 `docker compose down -v` 会发生什么？",
        "调用 __init__ 的时机是什么？",
        "GET /api/v1/documents 返回什么？",
        "`source_locator` 保存哪些信息？",
        "retrieval_min_score 在哪里配置？",
    ],
)
def test_hybrid_holdout_routes_exact_technical_identifiers_to_hybrid(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.HYBRID_TEXT
    assert decision.confidence == CONFIDENCE_HIGH


@pytest.mark.parametrize(
    "query",
    [
        "PostgreSQL MVCC 是什么？",
        "DeepSeek API 的配置方式是什么？",
        "block_aware 有什么特点？",
        "Python 类为什么有用？",
    ],
)
def test_hybrid_holdout_does_not_route_natural_language_technical_concepts_to_hybrid(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.CHUNK_ONLY


@pytest.mark.parametrize(
    "query",
    [
        "介绍一下依赖。",
        "权限和成员。",
        "这个东西有什么作用？",
    ],
)
def test_ambiguous_holdout_defaults_to_low_confidence_chunk_only(query: str) -> None:
    decision = route_query(query)

    assert decision.selected_mode == RetrievalMode.CHUNK_ONLY
    assert decision.confidence == CONFIDENCE_LOW


@pytest.mark.parametrize(
    ("manual_mode", "query"),
    [
        (RetrievalMode.HYBRID_TEXT, "Python 类是什么？"),
        (RetrievalMode.GRAPH_VECTOR_MIX, "介绍一下依赖。"),
    ],
)
def test_manual_holdout_modes_are_not_overridden_by_router(manual_mode: RetrievalMode, query: str) -> None:
    decision = _select_retrieval_mode(
        RetrievalRequest(
            query=query,
            knowledge_base_id=1,
            user_id=1,
            mode=manual_mode,
        )
    )

    assert decision.selected_mode == manual_mode
    assert decision.confidence == CONFIDENCE_MANUAL
    assert decision.reason == "manual mode specified"
