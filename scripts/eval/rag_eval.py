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
    category: str | None = None
    expected_mode: str | None = None
    expected_evidence_phrases: tuple[str, ...] = ()
    forbidden_evidence_phrases: tuple[str, ...] = ()
    expected_answerable: bool | None = None


@dataclass(frozen=True, slots=True)
class KeywordCoverageResult:
    coverage: float
    matched_keywords: tuple[str, ...] = ()
    missing_keywords: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RagEvalCaseResult:
    id: str
    mode: str
    retrieval_hit: bool | None
    citation_hit: bool | None
    keyword_coverage: float
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    used_reranker: bool
    trace_available: bool
    trace_id: int | str | None
    final_evidence_count: int
    top_documents: tuple[str, ...]
    top_1_doc_hit: bool | None
    top_3_doc_hit: bool | None
    trace_item_count: int | None = None
    initial_candidate_count: int | None = None
    requested_mode: str | None = None
    selected_mode: str | None = None
    router_reason: str | None = None
    latency_ms: int | None = None
    retrieval_latency_ms: int | None = None
    total_eval_latency_ms: int | None = None
    answer_contains_expected: bool | None = None
    category: str | None = None
    question: str | None = None
    expected_mode: str | None = None
    expected_doc_names: tuple[str, ...] = ()
    retrieved_doc_names: tuple[str, ...] = ()
    expected_evidence_phrases: tuple[str, ...] = ()
    forbidden_evidence_phrases: tuple[str, ...] = ()
    final_evidence_units: tuple[dict[str, Any], ...] = ()
    expected_evidence_hit: bool | None = None
    forbidden_evidence_hit: bool | None = None
    relevant_evidence_count: int | None = None
    irrelevant_evidence_count: int | None = None
    unknown_evidence_count: int | None = None
    evidence_precision: float | None = None
    router_accuracy: bool | None = None
    expected_answerable: bool | None = None
    predicted_answerable: bool | None = None
    answerability_accuracy: bool | None = None
    failure_reasons: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RagEvalSummary:
    total_cases: int
    retrieval_hit_rate: float
    citation_hit_rate: float
    average_keyword_coverage: float
    reranker_used_count: int
    trace_available_count: int
    top_1_doc_hit_rate: float
    top_3_doc_hit_rate: float
    average_latency_ms: float | None
    latency_summary: dict[str, float | int | None] = field(default_factory=dict)
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
        category=str(payload["category"]) if payload.get("category") is not None else None,
        expected_mode=str(payload["expected_mode"]) if payload.get("expected_mode") is not None else None,
        expected_evidence_phrases=tuple(
            str(item)
            for item in payload.get("expected_evidence_phrases", [])
            if str(item)
        ),
        forbidden_evidence_phrases=tuple(
            str(item)
            for item in payload.get("forbidden_evidence_phrases", [])
            if str(item)
        ),
        expected_answerable=(
            bool(payload["expected_answerable"])
            if payload.get("expected_answerable") is not None
            else None
        ),
    )


def evaluate_retrieval_result(
    case: RagEvalCase,
    result: RetrievalResult,
    *,
    trace_item_count: int | None = None,
    initial_candidate_count: int | None = None,
    latency_ms: int | None = None,
    retrieval_latency_ms: int | None = None,
    total_eval_latency_ms: int | None = None,
    retrieval_min_score: float = 0.0,
) -> RagEvalCaseResult:
    evidences = get_final_evidences(result)
    keyword_result = calculate_keyword_coverage(
        text=result.context_text,
        expected_keywords=case.expected_keywords,
    )
    top_documents = unique_document_names(evidences)
    final_evidence_units = tuple(evidence_to_dict(item) for item in evidences)
    expected_evidence_hit = calculate_expected_evidence_hit(
        evidences,
        expected_doc_names=case.expected_doc_names,
        expected_doc_ids=case.expected_doc_ids,
        expected_phrases=case.expected_evidence_phrases,
    )
    forbidden_evidence_hit = calculate_forbidden_evidence_hit(
        evidences,
        forbidden_phrases=case.forbidden_evidence_phrases,
    )
    evidence_classification = classify_evidence_units(
        evidences,
        expected_doc_names=case.expected_doc_names,
        expected_doc_ids=case.expected_doc_ids,
        expected_phrases=case.expected_evidence_phrases,
        forbidden_phrases=case.forbidden_evidence_phrases,
    )
    selected_mode = result.selected_mode.value if result.selected_mode else result.mode.value
    requested_mode = result.requested_mode.value if result.requested_mode else result.mode.value
    router_accuracy = selected_mode == case.expected_mode if requested_mode == "auto" and case.expected_mode else None
    predicted_answerable = bool(evidences) and has_reliable_evidence(
        evidences,
        min_score=retrieval_min_score,
    )
    answerability_accuracy = (
        predicted_answerable == case.expected_answerable
        if case.expected_answerable is not None
        else None
    )
    retrieval_hit = calculate_retrieval_hit(
        evidences,
        expected_doc_names=case.expected_doc_names,
        expected_doc_ids=case.expected_doc_ids,
    )
    citation_hit = calculate_citation_hit(
        evidences,
        expected_doc_names=case.expected_doc_names,
        expected_doc_ids=case.expected_doc_ids,
        expected_citation_required=case.expected_citation_required,
    )
    trace_available = result.trace_id is not None
    failure_reasons = classify_failure_reasons(
        retrieval_hit=retrieval_hit,
        citation_hit=citation_hit,
        trace_available=trace_available,
        expected_evidence_hit=expected_evidence_hit,
        forbidden_evidence_hit=forbidden_evidence_hit,
        router_accuracy=router_accuracy,
        expected_answerable=case.expected_answerable,
        predicted_answerable=predicted_answerable,
    )
    return RagEvalCaseResult(
        id=case.id,
        mode=case.mode,
        retrieval_hit=retrieval_hit,
        citation_hit=citation_hit,
        keyword_coverage=keyword_result.coverage,
        matched_keywords=keyword_result.matched_keywords,
        missing_keywords=keyword_result.missing_keywords,
        used_reranker=result.used_reranker,
        trace_available=trace_available,
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
        requested_mode=requested_mode,
        selected_mode=selected_mode,
        router_reason=result.router_reason,
        latency_ms=latency_ms,
        retrieval_latency_ms=retrieval_latency_ms if retrieval_latency_ms is not None else latency_ms,
        total_eval_latency_ms=total_eval_latency_ms if total_eval_latency_ms is not None else latency_ms,
        category=case.category,
        question=case.question,
        expected_mode=case.expected_mode,
        expected_doc_names=case.expected_doc_names,
        retrieved_doc_names=top_documents,
        expected_evidence_phrases=case.expected_evidence_phrases,
        forbidden_evidence_phrases=case.forbidden_evidence_phrases,
        final_evidence_units=final_evidence_units,
        expected_evidence_hit=expected_evidence_hit,
        forbidden_evidence_hit=forbidden_evidence_hit,
        relevant_evidence_count=evidence_classification["relevant"],
        irrelevant_evidence_count=evidence_classification["irrelevant"],
        unknown_evidence_count=evidence_classification["unknown"],
        evidence_precision=calculate_evidence_precision(
            relevant=evidence_classification["relevant"],
            irrelevant=evidence_classification["irrelevant"],
        ),
        router_accuracy=router_accuracy,
        expected_answerable=case.expected_answerable,
        predicted_answerable=predicted_answerable,
        answerability_accuracy=answerability_accuracy,
        failure_reasons=failure_reasons,
    )


def failed_case_result(case: RagEvalCase, *, error: str) -> RagEvalCaseResult:
    keyword_result = calculate_keyword_coverage(
        text="",
        expected_keywords=case.expected_keywords,
    )
    return RagEvalCaseResult(
        id=case.id,
        mode=case.mode,
        retrieval_hit=False if case.expected_doc_names or case.expected_doc_ids else None,
        citation_hit=False if case.expected_citation_required else None,
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
        category=case.category,
        question=case.question,
        expected_mode=case.expected_mode,
        expected_doc_names=case.expected_doc_names,
        retrieved_doc_names=(),
        expected_evidence_phrases=case.expected_evidence_phrases,
        forbidden_evidence_phrases=case.forbidden_evidence_phrases,
        final_evidence_units=(),
        expected_evidence_hit=None if not case.expected_evidence_phrases else False,
        forbidden_evidence_hit=None if not case.forbidden_evidence_phrases else False,
        relevant_evidence_count=0,
        irrelevant_evidence_count=0,
        unknown_evidence_count=0,
        evidence_precision=None,
        expected_answerable=case.expected_answerable,
        predicted_answerable=False,
        answerability_accuracy=(
            False == case.expected_answerable
            if case.expected_answerable is not None
            else None
        ),
        failure_reasons=("unexpected_no_answer",) if case.expected_answerable else (),
        error=error,
    )


def summarize_results(results: list[RagEvalCaseResult]) -> RagEvalSummary:
    total = len(results)
    latencies = [
        item.latency_ms
        for item in results
        if item.latency_ms is not None
    ]
    latency_summary = summarize_latencies(
        item.total_eval_latency_ms if item.total_eval_latency_ms is not None else item.latency_ms
        for item in results
    )
    return RagEvalSummary(
        total_cases=total,
        retrieval_hit_rate=_nullable_metric(item.retrieval_hit for item in results)["rate"] or 0.0,
        citation_hit_rate=_nullable_metric(item.citation_hit for item in results)["rate"] or 0.0,
        average_keyword_coverage=(
            sum(item.keyword_coverage for item in results) / total
            if total
            else 0.0
        ),
        reranker_used_count=sum(1 for item in results if item.used_reranker),
        trace_available_count=sum(1 for item in results if item.trace_available),
        top_1_doc_hit_rate=_nullable_metric(item.top_1_doc_hit for item in results)["rate"] or 0.0,
        top_3_doc_hit_rate=_nullable_metric(item.top_3_doc_hit for item in results)["rate"] or 0.0,
        average_latency_ms=sum(latencies) / len(latencies) if latencies else None,
        latency_summary=latency_summary,
        cases=tuple(results),
    )


def calculate_retrieval_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
) -> bool | None:
    if not expected_doc_names and not expected_doc_ids:
        return None
    return any(_evidence_matches_expected(item, expected_doc_names, expected_doc_ids) for item in evidences)


def calculate_citation_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
    expected_citation_required: bool,
) -> bool | None:
    if not expected_citation_required:
        return None
    has_expected_docs = bool(expected_doc_names or expected_doc_ids)
    return any(
        item.citation_unit_id is not None
        and bool(item.source_locator)
        and (
            _evidence_matches_expected(item, expected_doc_names, expected_doc_ids)
            if has_expected_docs
            else True
        )
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
) -> bool | None:
    if n <= 0:
        return False
    if not expected_doc_names and not expected_doc_ids:
        return None
    return calculate_retrieval_hit(
        list(evidences)[:n],
        expected_doc_names=expected_doc_names,
        expected_doc_ids=expected_doc_ids,
    )


def calculate_expected_evidence_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
    expected_phrases: tuple[str, ...] | list[str],
) -> bool | None:
    if not expected_phrases:
        return None
    return any(
        _evidence_matches_expected(item, expected_doc_names, expected_doc_ids)
        and any(_contains_keyword(item.text, phrase) for phrase in expected_phrases)
        for item in evidences
    )


def calculate_forbidden_evidence_hit(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    forbidden_phrases: tuple[str, ...] | list[str],
) -> bool | None:
    if not forbidden_phrases:
        return None
    return any(
        _contains_keyword(item.text, phrase)
        for item in evidences
        for phrase in forbidden_phrases
    )


def classify_evidence_units(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    expected_doc_names: tuple[str, ...] | list[str],
    expected_doc_ids: tuple[int, ...] | list[int] = (),
    expected_phrases: tuple[str, ...] | list[str],
    forbidden_phrases: tuple[str, ...] | list[str],
) -> dict[str, int]:
    relevant = 0
    irrelevant = 0
    unknown = 0
    has_expected_docs = bool(expected_doc_names or expected_doc_ids)
    for evidence in evidences:
        has_forbidden = any(_contains_keyword(evidence.text, phrase) for phrase in forbidden_phrases)
        expected_doc = (
            _evidence_matches_expected(evidence, expected_doc_names, expected_doc_ids)
            if has_expected_docs
            else True
        )
        has_expected_phrase = any(_contains_keyword(evidence.text, phrase) for phrase in expected_phrases)
        if has_forbidden or not expected_doc:
            irrelevant += 1
        elif expected_phrases and has_expected_phrase:
            relevant += 1
        else:
            unknown += 1
    return {"relevant": relevant, "irrelevant": irrelevant, "unknown": unknown}


def calculate_evidence_precision(*, relevant: int, irrelevant: int) -> float | None:
    denominator = relevant + irrelevant
    if denominator <= 0:
        return None
    return relevant / denominator


def has_reliable_evidence(
    evidences: tuple[RetrievedEvidence, ...] | list[RetrievedEvidence],
    *,
    min_score: float,
) -> bool:
    if not evidences:
        return False
    threshold = max(0.0, float(min_score))
    return max(_evidence_score(item) for item in evidences) >= threshold


def classify_failure_reasons(
    *,
    retrieval_hit: bool | None,
    citation_hit: bool | None,
    trace_available: bool,
    expected_evidence_hit: bool | None,
    forbidden_evidence_hit: bool | None,
    router_accuracy: bool | None,
    expected_answerable: bool | None,
    predicted_answerable: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if retrieval_hit is False:
        reasons.append("expected_document_not_retrieved")
    if expected_evidence_hit is False:
        reasons.append("expected_evidence_not_selected")
    if forbidden_evidence_hit is True:
        reasons.append("forbidden_evidence_selected")
    if router_accuracy is False:
        reasons.append("router_mode_mismatch")
    if expected_answerable is True and not predicted_answerable:
        reasons.append("unexpected_no_answer")
    if expected_answerable is False and predicted_answerable:
        reasons.append("unexpected_answerable")
    if citation_hit is False:
        reasons.append("citation_missing")
    if not trace_available:
        reasons.append("trace_missing")
    return tuple(reasons)


def get_final_evidences(result: RetrievalResult) -> tuple[RetrievedEvidence, ...]:
    """Return the canonical final citation evidence used by eval metrics.

    RetrievalResult.evidences is populated after evidence-unit selection and,
    when enabled, after reranker alignment. The metadata lists keep raw and
    intermediate chunks for debugging; they are intentionally not used for
    final citation/evidence metrics.
    """

    return tuple(result.evidences)


def evidence_to_dict(evidence: RetrievedEvidence) -> dict[str, Any]:
    return {
        "document_name": evidence.document_name,
        "document_id": evidence.document_id,
        "text": evidence.text,
        "score": evidence.final_score,
        "vector_score": evidence.vector_score,
        "keyword_score": evidence.keyword_score,
        "graph_score": evidence.graph_score,
        "rerank_score": evidence.rerank_score,
        "source_locator": evidence.source_locator,
        "citation_unit_id": evidence.citation_unit_id,
        "chunk_id": str(evidence.chunk_id),
    }


def summarize_latencies(values: Any) -> dict[str, float | int | None]:
    numbers = sorted(int(item) for item in values if item is not None)
    if not numbers:
        return {"mean": None, "p50": None, "p95": None, "max": None}
    return {
        "mean": sum(numbers) / len(numbers),
        "p50": percentile(numbers, 50),
        "p95": percentile(numbers, 95),
        "max": max(numbers),
    }


def percentile(sorted_values: list[int], percentile_value: int) -> int:
    if not sorted_values:
        raise ValueError("percentile requires at least one value.")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (percentile_value / 100)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    fraction = rank - lower
    return round(sorted_values[lower] + ((sorted_values[upper] - sorted_values[lower]) * fraction))


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
        "top_1_doc_hit_rate": summary.top_1_doc_hit_rate,
        "top_3_doc_hit_rate": summary.top_3_doc_hit_rate,
        "average_latency_ms": summary.average_latency_ms,
        "latency_summary": summary.latency_summary,
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
        "requested_mode": result.requested_mode,
        "selected_mode": result.selected_mode,
        "router_reason": result.router_reason,
        "latency_ms": result.latency_ms,
        "retrieval_latency_ms": result.retrieval_latency_ms,
        "total_eval_latency_ms": result.total_eval_latency_ms,
        "answer_contains_expected": result.answer_contains_expected,
        "category": result.category,
        "question": result.question,
        "expected_mode": result.expected_mode,
        "expected_doc_names": list(result.expected_doc_names),
        "retrieved_doc_names": list(result.retrieved_doc_names),
        "expected_evidence_phrases": list(result.expected_evidence_phrases),
        "forbidden_evidence_phrases": list(result.forbidden_evidence_phrases),
        "final_evidence_units": list(result.final_evidence_units),
        "expected_evidence_hit": result.expected_evidence_hit,
        "forbidden_evidence_hit": result.forbidden_evidence_hit,
        "relevant_evidence_count": result.relevant_evidence_count,
        "irrelevant_evidence_count": result.irrelevant_evidence_count,
        "unknown_evidence_count": result.unknown_evidence_count,
        "evidence_precision": result.evidence_precision,
        "router_accuracy": result.router_accuracy,
        "expected_answerable": result.expected_answerable,
        "predicted_answerable": result.predicted_answerable,
        "answerability_accuracy": result.answerability_accuracy,
        "failure_reasons": list(result.failure_reasons),
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


def _evidence_score(evidence: RetrievedEvidence) -> float:
    for score in (
        evidence.final_score,
        evidence.rerank_score,
        evidence.vector_score,
        evidence.keyword_score,
        evidence.graph_score,
    ):
        if score is not None:
            return float(score)
    return 0.0


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


def _nullable_metric(values: Any) -> dict[str, int | float | None]:
    filtered = [bool(item) for item in values if item is not None]
    if not filtered:
        return {"passed": 0, "applicable": 0, "rate": None}
    passed = sum(1 for item in filtered if item)
    return {"passed": passed, "applicable": len(filtered), "rate": passed / len(filtered)}
