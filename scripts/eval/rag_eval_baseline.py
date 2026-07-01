from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from scripts.eval.rag_eval import RagEvalCaseResult, RagEvalSummary, summarize_results


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    name: str
    chunk_strategy: str
    mode: str
    purpose: str


@dataclass(frozen=True, slots=True)
class RagEvalBaselineCase:
    id: str
    question: str
    expected_answer_contains: tuple[str, ...]
    expected_source_hint: str
    case_type: str
    expected_mode: str
    top_k: int = 8
    notes: str | None = None


BASELINES: tuple[BaselineConfig, ...] = (
    BaselineConfig(
        name="fixed_chunk_only",
        chunk_strategy="fixed",
        mode="chunk_only",
        purpose="Legacy fixed chunking with default vector retrieval.",
    ),
    BaselineConfig(
        name="block_aware_chunk_only",
        chunk_strategy="block_aware",
        mode="chunk_only",
        purpose="Isolates the effect of block-aware chunking under the default retrieval mode.",
    ),
    BaselineConfig(
        name="block_aware_hybrid_text",
        chunk_strategy="block_aware",
        mode="hybrid_text",
        purpose="Tests lexical recall for exact API paths, config keys, file paths, and technical tokens.",
    ),
    BaselineConfig(
        name="block_aware_graph_vector_mix",
        chunk_strategy="block_aware",
        mode="graph_vector_mix",
        purpose="Tests lightweight graph candidate merge plus vector candidates.",
    ),
    BaselineConfig(
        name="block_aware_auto",
        chunk_strategy="block_aware",
        mode="auto",
        purpose="Tests the M16 rule-based query router over the same block-aware KB.",
    ),
)

REQUIRED_SUMMARY_SECTIONS = (
    "# PureLink RAG Eval Baseline Summary",
    "## 1. Goal",
    "## 2. Evaluation Dataset",
    "## 3. Compared Baselines",
    "## 4. Metrics",
    "## 5. Results",
    "## 6. Findings",
    "### 6.1 Block-aware vs fixed",
    "### 6.2 Hybrid text retrieval",
    "### 6.3 Graph vector mix",
    "### 6.4 Auto router",
    "## 7. Limitations",
    "## 8. Reproduction Commands",
)


def default_baselines() -> tuple[BaselineConfig, ...]:
    return BASELINES


def load_baseline_cases(path: Path) -> list[RagEvalBaselineCase]:
    raw = path.read_text(encoding="utf-8")
    stripped = raw.strip()
    if not stripped:
        raise ValueError(f"No eval cases found at {path}.")

    if stripped.startswith("["):
        payload = json.loads(stripped)
        if not isinstance(payload, list):
            raise ValueError(f"Invalid eval cases at {path}: expected a JSON array.")
        return [
            parse_baseline_case(item, source=f"{path}:{index}")
            for index, item in enumerate(payload, start=1)
        ]

    cases: list[RagEvalBaselineCase] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(parse_baseline_case(json.loads(line), source=f"{path}:{line_number}"))
    if not cases:
        raise ValueError(f"No eval cases found at {path}.")
    return cases


def parse_baseline_case(payload: object, *, source: str = "case") -> RagEvalBaselineCase:
    if not isinstance(payload, dict):
        raise ValueError(f"{source}: expected object.")
    case_id = _required_str(payload, "id", source=source)
    question = _required_str(payload, "question", source=source)
    expected_source_hint = _required_str(payload, "expected_source_hint", source=source)
    expected_mode = _required_str(payload, "expected_mode", source=source)
    case_type = _required_str(payload, "case_type", source=source)
    expected_answer_contains = payload.get("expected_answer_contains", [])
    if not isinstance(expected_answer_contains, list) or not expected_answer_contains:
        raise ValueError(f"{source}: 'expected_answer_contains' must be a non-empty list.")
    return RagEvalBaselineCase(
        id=case_id,
        question=question,
        expected_answer_contains=tuple(str(item) for item in expected_answer_contains if str(item)),
        expected_source_hint=expected_source_hint,
        case_type=case_type,
        expected_mode=expected_mode,
        top_k=int(payload.get("top_k") or 8),
        notes=str(payload["notes"]) if payload.get("notes") is not None else None,
    )


def source_paths_for_cases(cases: list[RagEvalBaselineCase]) -> tuple[str, ...]:
    seen: set[str] = set()
    paths: list[str] = []
    for case in cases:
        if case.expected_source_hint in seen:
            continue
        seen.add(case.expected_source_hint)
        paths.append(case.expected_source_hint)
    return tuple(paths)


def summarize_baseline_results(results: list[RagEvalCaseResult]) -> RagEvalSummary:
    return summarize_results(results)


def baseline_summary_to_dict(
    *,
    baseline: BaselineConfig,
    summary: RagEvalSummary,
) -> dict[str, Any]:
    selected_modes = Counter(
        item.selected_mode
        for item in summary.cases
        if item.selected_mode
    )
    return {
        "name": baseline.name,
        "chunk_strategy": baseline.chunk_strategy,
        "mode": baseline.mode,
        "purpose": baseline.purpose,
        "total_cases": summary.total_cases,
        "retrieval_hit_rate": summary.retrieval_hit_rate,
        "citation_hit_rate": summary.citation_hit_rate,
        "top_1_doc_hit_rate": summary.top_1_doc_hit_rate,
        "top_3_doc_hit_rate": summary.top_3_doc_hit_rate,
        "average_keyword_coverage": summary.average_keyword_coverage,
        "trace_available_rate": (
            summary.trace_available_count / summary.total_cases
            if summary.total_cases
            else 0.0
        ),
        "trace_available_count": summary.trace_available_count,
        "reranker_used_count": summary.reranker_used_count,
        "average_latency_ms": summary.average_latency_ms,
        "selected_mode_counts": dict(sorted(selected_modes.items())),
        "cases": [_case_result_to_dict(item) for item in summary.cases],
    }


def build_baseline_payload(
    *,
    cases_path: Path,
    cases: list[RagEvalBaselineCase],
    source_paths: tuple[str, ...],
    baseline_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases_path": cases_path.as_posix(),
        "case_count": len(cases),
        "case_type_counts": dict(sorted(Counter(case.case_type for case in cases).items())),
        "cases": [
            {
                "id": case.id,
                "case_type": case.case_type,
                "expected_mode": case.expected_mode,
                "expected_source_hint": case.expected_source_hint,
            }
            for case in cases
        ],
        "data_sources": list(source_paths),
        "baselines": baseline_summaries,
    }


def render_summary_markdown(payload: dict[str, Any]) -> str:
    baselines = payload.get("baselines", [])
    case_type_counts = payload.get("case_type_counts", {})
    data_sources = payload.get("data_sources", [])

    lines: list[str] = [
        "# PureLink RAG Eval Baseline Summary",
        "",
        "## 1. Goal",
        "",
        "Evaluate PureLink retrieval quality across fixed chunking, block-aware chunking, hybrid text retrieval, graph-vector mixed retrieval, and the rule-based auto router. The reported numbers are generated by `scripts/eval/run_rag_eval_baseline.py` against a temporary local KB built from repository docs.",
        "",
        "## 2. Evaluation Dataset",
        "",
        f"- Cases file: `{payload.get('cases_path')}`",
        f"- Case count: {payload.get('case_count')}",
        f"- Case types: {_format_counts(case_type_counts)}",
        "- Data sources:",
        *[f"  - `{path}`" for path in data_sources],
        "",
        "## 3. Compared Baselines",
        "",
        "| Baseline | Chunk Strategy | Retrieval Mode | Purpose |",
        "|---|---|---|---|",
    ]
    for item in baselines:
        lines.append(
            f"| `{item['name']}` | `{item['chunk_strategy']}` | `{item['mode']}` | {item['purpose']} |"
        )

    lines.extend(
        [
            "",
            "## 4. Metrics",
            "",
            "- `retrieval_hit`: final retrieved evidence includes the expected source document.",
            "- `citation_hit`: final citation-ready evidence includes the expected source document.",
            "- `top_1_doc_hit` / `top_3_doc_hit`: expected source appears in the first 1 or first 3 final evidence documents.",
            "- `keyword_coverage`: fraction of expected keywords found in retrieved context.",
            "- `trace_available`: retrieval wrote a trace id.",
            "- `selected_mode`: actual retrieval mode executed. For `auto`, this comes from the query router.",
            "- `router_reason`: rule-based router explanation for `auto` cases.",
            "- `latency_ms`: service-level retrieval latency measured by the runner.",
            "- `answer_contains_expected`: not calculated in this baseline because the runner evaluates retrieval only and does not call the LLM answer generator.",
            "",
            "## 5. Results",
            "",
            "| Baseline | retrieval_hit | citation_hit | top_1_doc_hit | top_3_doc_hit | keyword_coverage | trace_available | avg_latency_ms |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in baselines:
        lines.append(
            f"| `{item['name']}` | {_pct(item['retrieval_hit_rate'])} | {_pct(item['citation_hit_rate'])} | "
            f"{_pct(item['top_1_doc_hit_rate'])} | {_pct(item['top_3_doc_hit_rate'])} | "
            f"{_pct(item['average_keyword_coverage'])} | {_pct(item['trace_available_rate'])} | "
            f"{_number(item.get('average_latency_ms'))} |"
        )

    lines.extend(
        [
            "",
            "### Results by Case Type",
            "",
            "| Baseline | Case Type | retrieval_hit | citation_hit | keyword_coverage |",
            "|---|---|---:|---:|---:|",
            *_render_case_type_rows(payload),
        ]
    )

    lines.extend(
        [
            "",
            "## 6. Findings",
            "",
            "### 6.1 Block-aware vs fixed",
            "",
            _compare_two(
                baselines,
                left="fixed_chunk_only",
                right="block_aware_chunk_only",
                label="block-aware chunking under chunk_only",
            ),
            "",
            "### 6.2 Hybrid text retrieval",
            "",
            _compare_two(
                baselines,
                left="block_aware_chunk_only",
                right="block_aware_hybrid_text",
                label="hybrid_text over block-aware chunks",
            ),
            _case_type_note(
                payload,
                baseline_name="block_aware_hybrid_text",
                case_type="technical",
                label="technical/API/config cases",
            ),
            "",
            "### 6.3 Graph vector mix",
            "",
            _compare_two(
                baselines,
                left="block_aware_chunk_only",
                right="block_aware_graph_vector_mix",
                label="graph_vector_mix over block-aware chunks",
            ),
            _case_type_note(
                payload,
                baseline_name="block_aware_graph_vector_mix",
                case_type="relation",
                label="relation/dependency cases",
            ),
            "",
            "### 6.4 Auto router",
            "",
            _auto_router_summary(baselines),
            _case_type_note(
                payload,
                baseline_name="block_aware_auto",
                case_type="technical",
                label="technical/API/config cases routed by auto",
            ),
            _case_type_note(
                payload,
                baseline_name="block_aware_auto",
                case_type="relation",
                label="relation/dependency cases routed by auto",
            ),
            "",
            "## 7. Limitations",
            "",
            "- The dataset is repository-doc based and intentionally small, so it is a regression baseline, not a statistical benchmark.",
            "- The runner uses deterministic local hashed-bow embeddings to avoid external model downloads and API calls.",
            "- `answer_contains_expected` is not calculated because this baseline evaluates retrieval and citation evidence, not generated answers.",
            "- Fixed and block-aware chunking are compared by rebuilding separate temporary KBs because chunk strategy is decided during ingestion.",
            "- GraphRAG is the current lightweight local-rule graph index, not a full multi-hop graph reasoning system.",
            "",
            "## 8. Reproduction Commands",
            "",
            "```bash",
            ".venv/bin/python scripts/eval/run_rag_eval_baseline.py \\",
            "  --cases docs/interview/rag-eval-cases.json \\",
            "  --output docs/interview/rag-eval-baseline-results.json \\",
            "  --summary docs/interview/rag-eval-baseline-summary.md",
            "```",
            "",
            "The runner creates a temporary SQLite database and temporary vector store, then removes them after writing the JSON and Markdown reports.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_summary_markdown(markdown: str) -> None:
    missing = [section for section in REQUIRED_SUMMARY_SECTIONS if section not in markdown]
    if missing:
        raise ValueError(f"Summary markdown is missing required sections: {', '.join(missing)}")


def _case_result_to_dict(result: RagEvalCaseResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "mode": result.mode,
        "requested_mode": result.requested_mode,
        "selected_mode": result.selected_mode,
        "router_reason": result.router_reason,
        "retrieval_hit": result.retrieval_hit,
        "citation_hit": result.citation_hit,
        "top_1_doc_hit": result.top_1_doc_hit,
        "top_3_doc_hit": result.top_3_doc_hit,
        "keyword_coverage": result.keyword_coverage,
        "matched_keywords": list(result.matched_keywords),
        "missing_keywords": list(result.missing_keywords),
        "trace_available": result.trace_available,
        "trace_id": result.trace_id,
        "trace_item_count": result.trace_item_count,
        "initial_candidate_count": result.initial_candidate_count,
        "used_reranker": result.used_reranker,
        "latency_ms": result.latency_ms,
        "answer_contains_expected": result.answer_contains_expected,
        "final_evidence_count": result.final_evidence_count,
        "top_documents": list(result.top_documents),
        **({"error": result.error} if result.error else {}),
    }


def _format_counts(counts: object) -> str:
    if not isinstance(counts, dict) or not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _pct(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value * 100:.1f}%"


def _number(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:.1f}"


def _baseline_by_name(baselines: object, name: str) -> dict[str, Any] | None:
    if not isinstance(baselines, list):
        return None
    for item in baselines:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _compare_two(
    baselines: object,
    *,
    left: str,
    right: str,
    label: str,
) -> str:
    left_item = _baseline_by_name(baselines, left)
    right_item = _baseline_by_name(baselines, right)
    if left_item is None or right_item is None:
        return f"No comparison available for {label}; one or both baselines are missing."

    retrieval_delta = right_item["retrieval_hit_rate"] - left_item["retrieval_hit_rate"]
    citation_delta = right_item["citation_hit_rate"] - left_item["citation_hit_rate"]
    keyword_delta = right_item["average_keyword_coverage"] - left_item["average_keyword_coverage"]
    return (
        f"`{right}` vs `{left}`: retrieval_hit delta {_signed_pct(retrieval_delta)}, "
        f"citation_hit delta {_signed_pct(citation_delta)}, "
        f"keyword_coverage delta {_signed_pct(keyword_delta)}. "
        f"This supports the comparison for {label} without assuming improvement where the data does not show it."
    )


def _auto_router_summary(baselines: object) -> str:
    item = _baseline_by_name(baselines, "block_aware_auto")
    if item is None:
        return "No auto baseline was produced."
    counts = item.get("selected_mode_counts", {})
    return (
        f"`block_aware_auto` selected modes: {_format_counts(counts)}. "
        f"Its retrieval_hit was {_pct(item.get('retrieval_hit_rate'))}, "
        f"citation_hit was {_pct(item.get('citation_hit_rate'))}, and "
        f"keyword_coverage was {_pct(item.get('average_keyword_coverage'))}."
    )


def _render_case_type_rows(payload: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    baselines = payload.get("baselines")
    if not isinstance(baselines, list):
        return rows
    case_types = sorted(
        {
            str(case.get("case_type"))
            for case in payload.get("cases", [])
            if isinstance(case, dict) and case.get("case_type")
        }
    )
    for baseline in baselines:
        if not isinstance(baseline, dict):
            continue
        for case_type in case_types:
            metrics = _case_type_metrics(payload, baseline_name=str(baseline.get("name")), case_type=case_type)
            if metrics is None:
                continue
            rows.append(
                f"| `{baseline.get('name')}` | {case_type} | {_pct(metrics['retrieval_hit_rate'])} | "
                f"{_pct(metrics['citation_hit_rate'])} | {_pct(metrics['average_keyword_coverage'])} |"
            )
    return rows


def _case_type_note(
    payload: dict[str, Any],
    *,
    baseline_name: str,
    case_type: str,
    label: str,
) -> str:
    metrics = _case_type_metrics(payload, baseline_name=baseline_name, case_type=case_type)
    if metrics is None:
        return f"No {label} data was available for `{baseline_name}`."
    return (
        f"For {label}, `{baseline_name}` produced retrieval_hit {_pct(metrics['retrieval_hit_rate'])}, "
        f"citation_hit {_pct(metrics['citation_hit_rate'])}, and keyword_coverage "
        f"{_pct(metrics['average_keyword_coverage'])}."
    )


def _case_type_metrics(
    payload: dict[str, Any],
    *,
    baseline_name: str,
    case_type: str,
) -> dict[str, float] | None:
    case_type_by_id = {
        str(case["id"]): str(case["case_type"])
        for case in payload.get("cases", [])
        if isinstance(case, dict) and case.get("id") and case.get("case_type")
    }
    baseline = _baseline_by_name(payload.get("baselines"), baseline_name)
    if baseline is None:
        return None
    cases = [
        case
        for case in baseline.get("cases", [])
        if isinstance(case, dict) and case_type_by_id.get(str(case.get("id"))) == case_type
    ]
    if not cases:
        return None
    total = len(cases)
    return {
        "retrieval_hit_rate": sum(1 for case in cases if case.get("retrieval_hit")) / total,
        "citation_hit_rate": sum(1 for case in cases if case.get("citation_hit")) / total,
        "average_keyword_coverage": sum(
            float(case.get("keyword_coverage") or 0.0)
            for case in cases
        ) / total,
    }


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.1f}pp"


def _required_str(payload: dict[str, Any], field_name: str, *, source: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: '{field_name}' is required.")
    return value.strip()


__all__ = [
    "BASELINES",
    "BaselineConfig",
    "REQUIRED_SUMMARY_SECTIONS",
    "RagEvalBaselineCase",
    "baseline_summary_to_dict",
    "build_baseline_payload",
    "default_baselines",
    "load_baseline_cases",
    "parse_baseline_case",
    "render_summary_markdown",
    "source_paths_for_cases",
    "summarize_baseline_results",
    "validate_summary_markdown",
]
