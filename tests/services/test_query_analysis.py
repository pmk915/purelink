from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.query_analysis import analyze_evidence_query, resolve_target_documents


def _documents(*filenames: str):
    return [
        SimpleNamespace(id=index, original_filename=filename)
        for index, filename in enumerate(filenames, start=1)
    ]


@pytest.mark.parametrize(
    ("query", "filenames", "expected_ids"),
    [
        ("概括 fastapi-dependencies.md", ("fastapi-dependencies.md",), (1,)),
        ("总结 Python classes 文档", ("tests/eval/corpus/python_classes.txt",), (1,)),
        ("总结 Python classes 文档", ("python_classes.txt",), (1,)),
        ("SUMMARIZE FASTAPI DEPENDENCIES", ("FastAPI-Dependencies.MD",), (1,)),
        ("概括 deployment guide", ("deployment_guide.pdf",), (1,)),
        ("请总结 Python classes 这份文档", ("python-classes.txt",), (1,)),
        ("What does the deployment guide cover?", ("deployment-guide.docx",), (1,)),
        ("总结 PureLink retrieval-guide 文档", ("purelink_retrieval_guide.md",), (1,)),
        (
            "Summarize the deployment production document",
            ("deployment-production-guide.md",),
            (1,),
        ),
    ],
)
def test_resolve_target_documents_matches_filename_variants(
    query: str,
    filenames: tuple[str, ...],
    expected_ids: tuple[int, ...],
) -> None:
    decision = resolve_target_documents(query, _documents(*filenames))

    assert decision.target_requested is True
    assert decision.target_document_ids == expected_ids
    assert decision.confidence in {"high", "medium"}
    assert decision.matched_terms


@pytest.mark.parametrize(
    "query",
    [
        "总结当前知识库",
        "这个知识库主要包含什么？",
        "Give me an overview of all documents",
        "总结一下",
        "当前语料中的团队成员有哪些？",
    ],
)
def test_resolve_target_documents_preserves_kb_wide_overview(query: str) -> None:
    decision = resolve_target_documents(
        query,
        _documents("python_classes.txt", "deployment-guide.md"),
    )

    assert decision.target_requested is False
    assert decision.target_document_ids == ()
    assert decision.reason == "knowledge_base_overview"


def test_resolve_target_documents_marks_explicit_missing_target() -> None:
    decision = resolve_target_documents(
        "总结不存在的 billing-handbook 文档",
        _documents("employee-handbook.md", "billing-overview.md"),
    )

    assert decision.target_requested is True
    assert decision.target_document_ids == ()
    assert decision.confidence == "none"
    assert decision.reason == "requested_document_not_found"


def test_resolve_target_documents_does_not_select_similar_longer_filename() -> None:
    decision = resolve_target_documents(
        "总结 deployment guide 文档",
        _documents("deployment-guide.md", "deployment-guide-archive.md"),
    )

    assert decision.target_document_ids == (1,)
    assert decision.matched_terms == ("deployment guide",)


def test_resolve_target_documents_supports_multiple_explicit_targets() -> None:
    decision = resolve_target_documents(
        "总结 deployment guide 和 operations handbook 文档",
        _documents("deployment-guide.md", "operations_handbook.pdf", "security-guide.md"),
    )

    assert decision.target_requested is True
    assert decision.target_document_ids == (1, 2)
    assert decision.matched_terms == ("deployment guide", "operations handbook")


def test_resolve_target_documents_does_not_force_single_generic_token_match() -> None:
    decision = resolve_target_documents(
        "概括 production 文档",
        _documents("production-deployment-guide.md", "production-operations-guide.md"),
    )

    assert decision.target_requested is True
    assert decision.target_document_ids == ()
    assert decision.reason == "requested_document_not_found"


@pytest.mark.parametrize(
    ("query", "expected_attributes"),
    [
        ("Alice Chen 在哪里办公？", ("location",)),
        ("Where is Alice Chen's office location?", ("location",)),
        ("Aurora Mini 使用哪款处理器？", ("processor",)),
        ("PureLink 支持哪些文本文件类型？", ("file_types",)),
        ("CHUNK_STRATEGY 支持哪些值？", ("supported_values",)),
        ("RETRIEVAL_MIN_SCORE 默认值是什么？", ("default_value",)),
        ("Aurora Mini 的颜色和处理器是什么？", ("processor", "color")),
    ],
)
def test_analyze_evidence_query_extracts_requested_attributes(
    query: str,
    expected_attributes: tuple[str, ...],
) -> None:
    analysis = analyze_evidence_query(query)

    assert set(analysis.requested_attributes) == set(expected_attributes)


@pytest.mark.parametrize(
    ("query", "expected_identifier"),
    [
        ("`CHUNK_STRATEGY` 支持哪些值？", "CHUNK_STRATEGY"),
        ("docker compose down -v 会发生什么？", "docker compose down -v"),
        ("GET /api/v1/documents 返回什么？", "GET /api/v1/documents"),
        ("app/services/qa.py 在哪里？", "app/services/qa.py"),
        ("process_document() 如何调用？", "process_document()"),
    ],
)
def test_analyze_evidence_query_extracts_technical_identifiers(
    query: str,
    expected_identifier: str,
) -> None:
    analysis = analyze_evidence_query(query)

    assert expected_identifier in analysis.technical_identifiers


def test_analyze_evidence_query_does_not_treat_ordinary_english_as_identifier() -> None:
    analysis = analyze_evidence_query("What makes Python classes useful?")

    assert analysis.technical_identifiers == ()


def test_analyze_evidence_query_extracts_contextual_framework_identifier() -> None:
    analysis = analyze_evidence_query("FastAPI 中 Depends 的作用是什么？")

    assert analysis.technical_identifiers == ("Depends",)
