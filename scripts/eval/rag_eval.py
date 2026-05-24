from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from app.services.retrieval.types import RetrievedEvidence, RetrievalResult


@dataclass(frozen=True, slots=True)
class RagEvalCase:
    id: str
    question: str
    knowledge_base_id: int
    user_id: int = 1
    mode: str = "chunk_only"
    top_k: int = 8
    expected_doc_names: tuple[str, ...] = ()
    expected_doc_ids: tuple[int, ...] = ()
    expected_keywords: tuple[str, ...] = ()
    expected_citation_required: bool = True
    notes: str | None = None
    scope: str | None = None
    team_id: int | None = None


@dataclass(frozen=True, slots=True)
class KeywordCoverageResult:
    coverage: float
    matched_keywords: tuple[str, ...] = ()
    missing_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagEvalCaseResult:
    id: str
    mode: str
    retrieval_hit: bool
    citation_hit: bool
    keyword_coverage: float
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    used_reranker: bool
    trace_available: bool
    trace_id: int | str | None
    final_evidence_count: int
    top_documents: tuple[str, ...]
    top_1_doc_hit: bool
    top_3_doc_hit: bool
    trace_item_count: int | None = None
    initial_candidate_count: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RagEvalSummary:
    total_cases: int
    retrieval_hit_rate: float
    citation_hit_rate: float
    average_keyword_coverage: float
    reranker_used_count: int
    trace_available_count: int
    cases: tuple[RagEvalCaseResult, ...] = field(default_factory=tuple)


def load_cases(path: Path) -> list[RagEvalCase]:
    cases: list[RagEvalCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid eval case at {path}:{line_number}: expected object.")
        cases.append(parse_case(payload, source=f"{path}:{line_number}"))
    return cases


def parse_case(payload: dict[str, Any], *, source: str = "case") -> RagEvalCase:
    case_id = _required_str(payload, "id", source=source)
    question = _required_str(payload, "question", source=source)
    knowledge_base_id = _required_int(payload, "knowledge_base_id", source=source)
    return RagEvalCase(
        id=case_id,
        question=question,
        knowledge_base_id=knowledge_base_id,
        user_id=_optional_int(payload, "user_id") or 1,
        mode=str(payload.get("mode") or "chunk_only"),
        top_k=int(payload.get("top_k") or 8),
        expected_doc_names=tuple(str(item) for item in payload.get("expected_doc_names", []) if str(item)),
        expected_doc_ids=tuple(int(item) for item in payload.get("expected_doc_ids", []) if item is not None),
        expected_keywords=tuple(str(item) for item in payload.get("expected_keywords", []) if str(item)),
        expected_citation_required=bool(payload.get("expected_citation_required", True)),
        notes=str(payload["notes"]) if payload.get("notes") is not None else None,
        scope=str(payload["scope"]) if payload.get("scope") is not None else None,
        team_id=_optional_int(payload, "team_id"),
    )


def evaluate_retrieval_result(
    case: RagEvalCase,
    result: RetrievalResult,
    *,
    trace_item_count: int | None = None,
    initial_candidate_count: int | None = None,
) -> RagEvalCaseResult:
    evidences = tuple(result.evidences)
    keyword_result = calculate_keyword_coverage(
        text=result.context_text,
        expected_keywords=case.expected_keywords,
    )
    top_documents = unique_document_names(evidences)
    return RagEvalCaseResult(
        id=case.id,
        mode=case.mode,
        retrieval_hit=calculate_retrieval_hit(
            evidences,
            expected_doc_names=case.expected_doc_names,
            expected_doc_ids=case.expected_doc_ids,
        ),
        citation_hit=calculate_citation_hit(
            evidences,
            expected_doc_names=case.expected_doc_names,
            expected_doc_ids=case.expected_doc_ids,
            expected_citation_required=case.expected_citation_required,
        ),
        keyword_coverage=keyword_result.coverage,
        matched_keywords=keyword_result.matched_keywords,
        missing_keywords=keyword_result.missing_keywords,
        used_reranker=result.used_reranker,
        trace_available=result.trace_id is not None,
        trace_id=result.trace_id,
        final_evidence_count=len(evidences),
        top_documents=top_documents,
        top_1_doc_hit=calculate_top_n_doc_hit(
            evidences,
            expected_doc_names=case.expected_doc_names,
            expected_doc_ids=case.expected_doc_ids,
            n=1,
        ),
        top_3_doc_hit=calculate_top_n_doc_hit(
            evidences,
            expected_doc_names=case.expected_doc_names,
            expected_doc_ids=case.expected_doc_ids,
            n=3,
        ),
        trace_item_count=trace_item_count,
        initial_candidate_count=initial_candidate_count,
    )


def failed_case_result(case: RagEvalCase, *, error: str) -> RagEvalCaseResult:
    keyword_result = calculate_keyword_coverage(
        text="",
        expected_keywords=case.expected_keywords,
    )
    return RagEvalCaseResult(
        id=case.id,
        mode=case.mode,
        retrieval_hit=False,
        citation_hit=not case.expected_citation_required,
        keyword_coverage=keyword_result.coverage,
        matched_keywords=keyword_result.matched_keywords,
        missing_keywords=keyword_result.missing_keywords,
        used_reranker=False,
        trace_available=False,
        trace_id=None,
        final_evidence_count=0,
        top_documents=(),
        top_1_doc_hit=False,
        top_3_doc_hit=False,
        error=error,
    )


def summarize_results(results: list[RagEvalCaseResult]) -> RagEvalSummary:
    total = len(results)
    return RagEvalSummary(
        total_cases=total,
        retrieval_hit_rate=_rate(sum(1 for item in results if item.retrieval_hit), total),
        citation_hit_rate=_rate(sum(1 for item in results if item.citation_hit), total),
        average_keyword_coverage=(
            sum(item.keyword_coverage for item in results) / total
            if total
            else 0.0
        ),
        reranker_used_count=sum(1 for item in results if item.used_reranker),
        trace_available_count=sum(1 for item in results if item.trace_available),
        cases=tuple(results),
    )


def calculate_retrieval_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
) -> bool:
    if not expected_doc_names and not expected_doc_ids:
        return True
    return any(_evidence_matches_expected(item, expected_doc_names, expected_doc_ids) for item in evidences)


def calculate_citation_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
    expected_citation_required: bool,
) -> bool:
    if not expected_citation_required:
        return True
    return any(
        item.citation_unit_id is not None
        and _evidence_matches_expected(item, expected_doc_names, expected_doc_ids)
        for item in evidences
    )


def calculate_keyword_coverage(
    *,
    text: str,
    expected_keywords: tuple[str, ...] | list[str],
) -> KeywordCoverageResult:
    if not expected_keywords:
        return KeywordCoverageResult(coverage=1.0)

    matched: list[str] = []
    missing: list[str] = []
    for keyword in expected_keywords:
        if _contains_keyword(text, keyword):
            matched.append(keyword)
        else:
            missing.append(keyword)
    return KeywordCoverageResult(
        coverage=len(matched) / len(expected_keywords),
        matched_keywords=tuple(matched),
        missing_keywords=tuple(missing),
    )


def calculate_top_n_doc_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
    n: int,
) -> bool:
    if n <= 0:
        return False
    return calculate_retrieval_hit(
        list(evidences)[:n],
        expected_doc_names=expected_doc_names,
        expected_doc_ids=expected_doc_ids,
    )


def unique_document_names(evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence]) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for evidence in evidences:
        if not evidence.document_name or evidence.document_name in seen:
            continue
        seen.add(evidence.document_name)
        names.append(evidence.document_name)
    return tuple(names)


def summary_to_dict(summary: RagEvalSummary) -> dict[str, Any]:
    return {
        "total_cases": summary.total_cases,
        "retrieval_hit_rate": summary.retrieval_hit_rate,
        "citation_hit_rate": summary.citation_hit_rate,
        "average_keyword_coverage": summary.average_keyword_coverage,
        "reranker_used_count": summary.reranker_used_count,
        "trace_available_count": summary.trace_available_count,
        "cases": [case_result_to_dict(item) for item in summary.cases],
    }


def case_result_to_dict(result: RagEvalCaseResult) -> dict[str, Any]:
    payload = {
        "id": result.id,
        "mode": result.mode,
        "retrieval_hit": result.retrieval_hit,
        "citation_hit": result.citation_hit,
        "keyword_coverage": result.keyword_coverage,
        "matched_keywords": list(result.matched_keywords),
        "missing_keywords": list(result.missing_keywords),
        "used_reranker": result.used_reranker,
        "trace_available": result.trace_available,
        "trace_id": result.trace_id,
        "final_evidence_count": result.final_evidence_count,
        "top_documents": list(result.top_documents),
        "top_1_doc_hit": result.top_1_doc_hit,
        "top_3_doc_hit": result.top_3_doc_hit,
        "trace_item_count": result.trace_item_count,
        "initial_candidate_count": result.initial_candidate_count,
    }
    if result.error:
        payload["error"] = result.error
    return payload


def _evidence_matches_expected(
    evidence: RetrievedEvidence,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int],
) -> bool:
    expected_names = {item.casefold() for item in expected_doc_names}
    if evidence.document_name and evidence.document_name.casefold() in expected_names:
        return True
    return evidence.document_id in set(expected_doc_ids)


def _contains_keyword(text: str, keyword: str) -> bool:
    if not keyword:
        return True
    return keyword.casefold() in text.casefold()


def _required_str(payload: dict[str, Any], field_name: str, *, source: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: '{field_name}' is required.")
    return value.strip()


def _required_int(payload: dict[str, Any], field_name: str, *, source: str) -> int:
    value = payload.get(field_name)
    if value is None:
        raise ValueError(f"{source}: '{field_name}' is required.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source}: '{field_name}' must be an integer.") from exc


def _optional_int(payload: dict[str, Any], field_name: str) -> int | None:
    value = payload.get(field_name)
    if value is None or value == "":
        return None
    return int(value)


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0
