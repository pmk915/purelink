from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.query_analysis import resolve_target_documents


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
