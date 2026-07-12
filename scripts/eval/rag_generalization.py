from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from scripts.eval.rag_eval import RagEvalCase, RagEvalCaseResult, case_result_to_dict, summarize_latencies


REQUIRED_CORPUS_FILES = (
    "python_classes.txt",
    "fastapi_dependencies.txt",
    "postgresql_concurrency.txt",
    "alice_characters.txt",
    "acme_team_roles.txt",
    "device_catalog.txt",
    "employee_policy.txt",
    "purelink_retrieval.txt",
    "purelink_processing.txt",
)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(api[_-]?key|password|secret)\s*=\s*['\"]?[A-Za-z0-9_-]{12,}"),
)
PLACEHOLDER_TOKENS = ("TODO", "TBD", "lorem ipsum", "placeholder")


def validate_corpus(corpus_dir: Path, cases: list[RagEvalCase]) -> list[dict[str, Any]]:
    if not corpus_dir.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    manifest = build_corpus_manifest(corpus_dir)
    names = {item["name"] for item in manifest}
    missing = [name for name in REQUIRED_CORPUS_FILES if name not in names]
    if missing:
        raise ValueError(f"Missing corpus files: {', '.join(missing)}")
    if len(names) != len(manifest):
        raise ValueError("Corpus file names must be unique.")

    for item in manifest:
        if item["char_count"] < 800 or item["char_count"] > 2500:
            raise ValueError(f"{item['path']} must be 800-2500 characters; got {item['char_count']}.")
        if item["heading_count"] < 2:
            raise ValueError(f"{item['path']} must contain at least two headings.")
        text = (corpus_dir / item["name"]).read_text(encoding="utf-8")
        lowered = text.casefold()
        if any(token.casefold() in lowered for token in PLACEHOLDER_TOKENS):
            raise ValueError(f"{item['path']} contains a placeholder token.")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise ValueError(f"{item['path']} appears to contain a secret.")

    corpus_paths = {f"tests/eval/corpus/{name}" for name in names}
    referenced = {
        doc_name
        for case in cases
        for doc_name in case.expected_doc_names
        if doc_name.startswith("tests/eval/corpus/")
    }
    unknown = sorted(referenced - corpus_paths)
    if unknown:
        raise ValueError(f"Cases reference missing corpus docs: {', '.join(unknown)}")
    return manifest


def build_corpus_manifest(corpus_dir: Path) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for path in sorted(corpus_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        manifest.append(
            {
                "name": path.name,
                "path": f"tests/eval/corpus/{path.name}",
                "char_count": len(text),
                "heading_count": len(re.findall(r"(?m)^#{1,6}\s+", text)),
                "sha256": _sha256_text(text),
            }
        )
    return manifest


def build_run_id(*, mode: str, chunk_strategy: str, created_at: datetime | None = None) -> str:
    timestamp = (created_at or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{mode}-{chunk_strategy}"


def build_run_metadata(
    *,
    run_id: str,
    created_at: datetime,
    case_file: Path,
    corpus_manifest: list[dict[str, Any]],
    case_count: int,
    chunk_strategy: str,
    requested_mode: str,
    settings: Any,
    duration_ms: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "created_at": created_at.isoformat(),
        "commit_sha": git_commit_sha(),
        "dirty_worktree": git_worktree_dirty(),
        "case_file": case_file.as_posix(),
        "corpus_manifest": corpus_manifest,
        "case_count": case_count,
        "chunk_strategy": chunk_strategy,
        "requested_mode": requested_mode,
        "embedding_provider": getattr(settings, "embedding_provider", None),
        "embedding_model": getattr(settings, "embedding_model", None),
        "reranker_enabled": bool(getattr(settings, "reranker_enabled", False)),
        "reranker_provider": getattr(settings, "reranker_provider", None),
        "retrieval_min_score": getattr(settings, "retrieval_min_score", None),
        "python_version": sys.version.split()[0],
        "duration_ms": duration_ms,
    }


def results_payload(results: list[RagEvalCaseResult]) -> dict[str, Any]:
    return {"case_count": len(results), "cases": [case_result_to_dict(item) for item in results]}


def write_sanitized_snapshot(
    *,
    snapshot_dir: Path,
    run_payload: dict[str, Any],
    results_json: dict[str, Any],
    summary_markdown: str,
) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "run.json").write_text(
        json.dumps(sanitize_run_payload(run_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (snapshot_dir / "results.json").write_text(
        json.dumps(sanitize_results_payload(results_json), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (snapshot_dir / "summary.md").write_text(summary_markdown, encoding="utf-8")


def sanitize_run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "run_id",
        "created_at",
        "commit_sha",
        "dirty_worktree",
        "case_file",
        "corpus_manifest",
        "case_count",
        "case_category_counts",
        "chunk_strategy",
        "requested_mode",
        "embedding_provider",
        "embedding_model",
        "reranker_enabled",
        "reranker_provider",
        "retrieval_min_score",
        "python_version",
        "duration_ms",
    }
    sanitized = {key: payload[key] for key in allowed_keys if key in payload}
    sanitized["corpus_manifest"] = [
        {
            "name": item.get("name"),
            "path": _repo_relative_path(str(item.get("path", ""))),
            "char_count": item.get("char_count"),
            "heading_count": item.get("heading_count"),
            "sha256": item.get("sha256"),
        }
        for item in payload.get("corpus_manifest", [])
    ]
    return sanitized


def sanitize_results_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_count": payload.get("case_count"),
        "cases": [_sanitize_case_result(item) for item in payload.get("cases", [])],
    }


def render_summary_markdown(*, run_metadata: dict[str, Any], results: list[RagEvalCaseResult]) -> str:
    overall = _overall_metrics(results)
    by_category = _group_metrics(results, key=lambda item: item.category or "uncategorized")
    by_mode = _group_metrics(results, key=lambda item: item.selected_mode or "unknown")
    no_answer = [item for item in results if item.category == "no_answer"]
    failed = [item for item in results if item.failure_reasons or item.error]
    latency = summarize_latencies(
        item.total_eval_latency_ms if item.total_eval_latency_ms is not None else item.latency_ms
        for item in results
    )

    lines = [
        "# PureLink RAG Generalization Eval Summary",
        "",
        "## 1. Run Configuration",
        "",
        f"- Run id: `{run_metadata['run_id']}`",
        f"- Created at: `{run_metadata['created_at']}`",
        f"- Commit: `{run_metadata['commit_sha']}`",
        f"- Dirty worktree: `{run_metadata['dirty_worktree']}`",
        f"- Case file: `{run_metadata['case_file']}`",
        f"- Case count: {run_metadata['case_count']}",
        f"- Chunk strategy: `{run_metadata['chunk_strategy']}`",
        f"- Requested mode: `{run_metadata['requested_mode']}`",
        f"- Embedding: `{run_metadata['embedding_provider']}` / `{run_metadata['embedding_model']}`",
        f"- Reranker: `{run_metadata['reranker_provider']}` enabled={run_metadata['reranker_enabled']}",
        "",
        "## 2. Overall Metrics",
        "",
        _metrics_table(overall),
        "",
        "## 3. Metrics by Category",
        "",
        _group_table(by_category),
        "",
        "## 4. Metrics by Selected Mode",
        "",
        _group_table(by_mode),
        "",
        "## 5. No-answer Results",
        "",
        _no_answer_table(no_answer),
        "",
        "## 6. Latency Summary",
        "",
        "In-process retrieval latency. Excludes ingestion, embedding/index construction, HTTP transport, LLM answer generation, and frontend rendering.",
        "",
        f"- mean: {_number(latency['mean'])} ms",
        f"- p50: {_number(latency['p50'])} ms",
        f"- p95: {_number(latency['p95'])} ms",
        f"- max: {_number(latency['max'])} ms",
        "",
        "## 7. Failed Cases",
        "",
        _failed_cases_table(failed),
        "",
        "## 8. Known Limitations",
        "",
        "- This baseline is deterministic and does not use LLM-as-judge.",
        "- Evidence precision is approximated with expected/forbidden phrases and expected document names.",
        "- Evidence-gate answerability uses the production deterministic Evidence Support Gate, including query-type mandatory checks and support signals.",
        "- Evidence support score is a debugging signal, not a semantic correctness score or LLM-as-judge result.",
        "- No-answer failures expose limitations of the production support gate, not full QA accuracy.",
        "- In-process retrieval latency is only useful for comparison on the same local environment.",
        "- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.",
        "",
    ]
    return "\n".join(lines)


def git_commit_sha() -> str:
    return _git_output(["git", "rev-parse", "--short", "HEAD"]) or "unknown"


def git_worktree_dirty() -> bool:
    return bool(_git_output(["git", "status", "--porcelain"]))


def _git_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sanitize_case_result(item: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "id",
        "mode",
        "category",
        "question",
        "requested_mode",
        "selected_mode",
        "router_reason",
        "expected_mode",
        "expected_doc_names",
        "retrieved_doc_names",
        "expected_evidence_phrases",
        "forbidden_evidence_phrases",
        "retrieval_hit",
        "citation_hit",
        "keyword_coverage",
        "matched_keywords",
        "missing_keywords",
        "expected_evidence_hit",
        "forbidden_evidence_hit",
        "relevant_evidence_count",
        "irrelevant_evidence_count",
        "unknown_evidence_count",
        "evidence_precision",
        "router_accuracy",
        "expected_answerable",
        "predicted_answerable",
        "answerability_accuracy",
        "final_evidence_count",
        "top_documents",
        "top_1_doc_hit",
        "top_3_doc_hit",
        "used_reranker",
        "trace_available",
        "retrieval_latency_ms",
        "total_eval_latency_ms",
        "failure_reasons",
        "error",
    }
    sanitized = {key: item.get(key) for key in allowed_keys if key in item}
    sanitized["final_evidence_units"] = [
        {
            "document_name": unit.get("document_name"),
            "text": unit.get("text"),
            "score": unit.get("score"),
            "vector_score": unit.get("vector_score"),
            "keyword_score": unit.get("keyword_score"),
            "graph_score": unit.get("graph_score"),
            "rerank_score": unit.get("rerank_score"),
            "source_locator": unit.get("source_locator"),
        }
        for unit in item.get("final_evidence_units", [])
    ]
    return sanitized


def _repo_relative_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.name
    return value


def _overall_metrics(results: list[RagEvalCaseResult]) -> dict[str, Any]:
    total = len(results)
    return _metrics_for_group(results, total=total)


def _group_metrics(results: list[RagEvalCaseResult], *, key) -> dict[str, dict[str, Any]]:  # noqa: ANN001
    grouped: dict[str, list[RagEvalCaseResult]] = defaultdict(list)
    for result in results:
        grouped[str(key(result))].append(result)
    return {
        group_name: _metrics_for_group(group_results, total=len(group_results))
        for group_name, group_results in sorted(grouped.items())
    }


def _metrics_for_group(results: list[RagEvalCaseResult], *, total: int) -> dict[str, Any]:
    return {
        "cases": total,
        "retrieval_hit": _nullable_metric(item.retrieval_hit for item in results),
        "citation_hit": _nullable_metric(item.citation_hit for item in results),
        "expected_evidence_hit": _nullable_metric(item.expected_evidence_hit for item in results),
        "forbidden_evidence_clean": _nullable_metric(
            False if item.forbidden_evidence_hit else True
            for item in results
            if item.forbidden_evidence_hit is not None
        ),
        "router_accuracy": _nullable_metric(item.router_accuracy for item in results),
        "answerability_accuracy": _nullable_metric(item.answerability_accuracy for item in results),
        "mean_evidence_precision": _mean_metric(item.evidence_precision for item in results),
        "trace_available": _nullable_metric(item.trace_available for item in results),
    }


def _metrics_table(metrics: dict[str, Any]) -> str:
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| cases | {metrics['cases']} |",
            f"| retrieval_hit | {_metric_count(metrics['retrieval_hit'])} |",
            f"| citation_hit | {_metric_count(metrics['citation_hit'])} |",
            f"| expected_evidence_hit | {_metric_count(metrics['expected_evidence_hit'])} |",
            f"| forbidden_evidence_clean | {_metric_count(metrics['forbidden_evidence_clean'])} |",
            f"| router_accuracy | {_metric_count(metrics['router_accuracy'])} |",
            f"| evidence-gate answerability_accuracy | {_metric_count(metrics['answerability_accuracy'])} |",
            f"| mean_evidence_precision | {_mean_count(metrics['mean_evidence_precision'])} |",
            f"| trace_available | {_metric_count(metrics['trace_available'])} |",
        ]
    )


def _group_table(grouped: dict[str, dict[str, Any]]) -> str:
    lines = [
        "| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group, metrics in grouped.items():
        lines.append(
            f"| `{group}` | {metrics['cases']} | {_metric_count(metrics['retrieval_hit'])} | "
            f"{_metric_count(metrics['citation_hit'])} | {_metric_count(metrics['expected_evidence_hit'])} | "
            f"{_metric_count(metrics['router_accuracy'])} | {_metric_count(metrics['answerability_accuracy'])} | "
            f"{_mean_count(metrics['mean_evidence_precision'])} |"
        )
    return "\n".join(lines)


def _no_answer_table(results: list[RagEvalCaseResult]) -> str:
    if not results:
        return "No no-answer cases."
    lines = [
        "| Case | retrieval_hit | citation_hit | expected_evidence_hit | predicted_answerable | evidence-gate answerability | forbidden_evidence_hit | failure_reasons |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in results:
        lines.append(
            f"| `{item.id}` | {_bool_or_na(item.retrieval_hit)} | {_bool_or_na(item.citation_hit)} | "
            f"{_bool_or_na(item.expected_evidence_hit)} | {item.predicted_answerable} | "
            f"{_bool_or_na(item.answerability_accuracy)} | {_bool_or_na(item.forbidden_evidence_hit)} | "
            f"{', '.join(item.failure_reasons) or '-'} |"
        )
    return "\n".join(lines)


def _failed_cases_table(results: list[RagEvalCaseResult]) -> str:
    if not results:
        return "No failed cases."
    lines = ["| Case | Question | Expected | Actual | Selected Mode | Failure Reason |", "|---|---|---|---|---|---|"]
    for item in results:
        expected = ", ".join(item.expected_evidence_phrases or item.expected_doc_names or ())
        actual = "; ".join(
            str(unit.get("text", ""))[:120].replace("\n", " ")
            for unit in item.final_evidence_units[:2]
        )
        lines.append(
            f"| `{item.id}` | {item.question or ''} | {expected or '-'} | {actual or '-'} | "
            f"`{item.selected_mode or 'unknown'}` | {', '.join(item.failure_reasons) or item.error or '-'} |"
        )
    return "\n".join(lines)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _nullable_metric(values: Any) -> dict[str, int | float | None]:
    filtered = [bool(item) for item in values if item is not None]
    if not filtered:
        return {"passed": 0, "applicable": 0, "rate": None}
    passed = sum(1 for item in filtered if item)
    return {"passed": passed, "applicable": len(filtered), "rate": passed / len(filtered)}


def _mean_metric(values: Any) -> dict[str, float | int | None]:
    numbers = [float(item) for item in values if item is not None]
    if not numbers:
        return {"mean": None, "applicable": 0}
    return {"mean": sum(numbers) / len(numbers), "applicable": len(numbers)}


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _pct_or_na(value: float | None) -> str:
    if value is None:
        return "n/a"
    return _pct(value)


def _metric_count(metric: dict[str, int | float | None]) -> str:
    applicable = int(metric["applicable"] or 0)
    if applicable == 0:
        return "n/a"
    passed = int(metric["passed"] or 0)
    return f"{passed} / {applicable} ({_pct(float(metric['rate'] or 0.0))})"


def _mean_count(metric: dict[str, float | int | None]) -> str:
    applicable = int(metric["applicable"] or 0)
    if applicable == 0:
        return "n/a"
    return f"{_pct(float(metric['mean'] or 0.0))} (n={applicable})"


def _bool_or_na(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "true" if value else "false"


def _number(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.1f}"


def category_counts(cases: list[RagEvalCase]) -> dict[str, int]:
    return dict(sorted(Counter(case.category or "uncategorized" for case in cases).items()))
