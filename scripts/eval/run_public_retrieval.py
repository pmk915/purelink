"""Explicit developer-only official NanoBEIR evaluation; no QA/product flows."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
import time
import warnings

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.public_retrieval import (
    ENGLISH_MODEL, METRICS, aggregate_results, benchmark_environment,
    canonical_qrels, capture_config, corpus_text, evaluate_rankings,
    purelink_index, purelink_rankings, ranking_scores,
    model_source_revision, select_task_names,
)


class DirectFastEmbedEncoder:
    """Embedding-only MTEB v2 encoder; official MTEB performs dense search.

    No PureLink provider, index, scorer, keyword fusion, or reranker is used.
    FastEmbed's quantized ONNX artifact is shared by all configurations.
    """

    def __init__(self, cache_root: Path):
        from fastembed import TextEmbedding
        from mteb.models import ModelMeta

        self.model = TextEmbedding(model_name=ENGLISH_MODEL, cache_dir=str(cache_root / "models"),
                                   providers=["CPUExecutionProvider"], threads=4)
        self.mteb_model_meta = ModelMeta.create_empty(overwrites={
            "name": ENGLISH_MODEL, "revision": model_source_revision(cache_root), "embed_dim": 384,
            "framework": ["ONNX"], "similarity_fn_name": "cosine",
            "experiment_kwargs": {"backend": "fastembed-quantized-onnx", "representation": "title-newline-text"},
        })

    def encode(self, inputs, *, prompt_type=None, **kwargs):
        import numpy as np

        vectors = []
        for batch in inputs:
            if str(prompt_type) == "document":
                bodies = batch.get("body", batch["text"])
                titles = batch.get("title", [""] * len(bodies))
                texts = [corpus_text({"title": title, "text": body}) for title, body in zip(titles, bodies, strict=True)]
                encode = self.model.passage_embed
            else:
                texts = batch.get("query", batch["text"])
                encode = self.model.query_embed
            vectors.extend(encode(texts, batch_size=kwargs.get("batch_size", 32)))
        array = np.asarray(vectors, dtype=np.float32)
        return array / np.linalg.norm(array, axis=1, keepdims=True)

    def similarity(self, left, right):
        import numpy as np
        left, right = np.asarray(left), np.asarray(right)
        return (left / np.linalg.norm(left, axis=-1, keepdims=True)) @ (right / np.linalg.norm(right, axis=-1, keepdims=True)).T

    def similarity_pairwise(self, left, right):
        import numpy as np
        left, right = np.asarray(left), np.asarray(right)
        return np.sum(left * right, axis=-1) / (np.linalg.norm(left, axis=-1) * np.linalg.norm(right, axis=-1))


def write_report(run_dir: Path, report: dict) -> None:
    report["aggregate"] = aggregate_results(report["tasks"], report["config"]["retrieval_modes"])
    (run_dir / "run.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Public Retrieval Validation", "", f"Baseline: `{report['config']['baseline_sha']}`. Run SHA: `{report['config']['commit_sha']}`; dirty={report['config']['dirty']}.",
             "", "Scope: " + report["config"].get("scope", "see task completion statuses") + ".",
             "", "BGE small English v1.5 via FastEmbed quantized ONNX; official qrels. Scores are fractions.", "",
             "| Task | Queries | Corpus | Configuration | nDCG@10 | Recall@10 | MRR@10 | Status |",
             "|---|---:|---:|---|---:|---:|---:|---|"]
    for task in report["tasks"]:
        for mode in report["config"]["retrieval_modes"]:
            result = task.get("results", {}).get(mode, {})
            scores = result.get("metrics", {})
            values = [f"{scores[metric]:.5f}" if metric in scores else "—" for metric in METRICS[:3]]
            status = result.get("status", task.get("status", "pending"))
            lines.append(f"| {task['task']} | {task.get('query_count', '—')} | {task.get('corpus_size', '—')} | {mode} | {' | '.join(values)} | {status} |")
            if result.get("reason"):
                lines.extend(["", f"{task['task']} / {mode}: {result['reason']}", ""])
    lines.extend(["", "Shared completed tasks: " + ", ".join(report["aggregate"]["shared_completed_tasks"]), ""])
    for mode, scores in report["aggregate"]["macro_mean"].items():
        lines.append(f"- {mode}: " + "; ".join(f"{metric}={value:.5f}" if value is not None else f"{metric}=unavailable" for metric, value in scores.items()))
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n")


def direct_evaluation(task, encoder, task_dir: Path) -> tuple[dict, dict]:
    import mteb

    # Standard official search/evaluation, limited to the required retrieval cutoffs.
    task.k_values = (1, 3, 5, 10)
    task._top_k = 10
    result = mteb.evaluate(encoder, [task], cache=None, co2_tracker=False,
                           prediction_folder=task_dir / "official-predictions",
                           show_progress_bar=False, encode_kwargs={"batch_size": 32}, num_proc=1)
    (task_dir / "official-result.json").write_text(result.model_dump_json(indent=2) + "\n")
    files = list((task_dir / "official-predictions").glob("*.json"))
    if len(files) != 1:
        raise ValueError("Expected one official retrieval prediction file.")
    predictions = json.loads(files[0].read_text())["default"]["train"]
    official = result.task_results[0].scores["train"][0]
    return {metric: official[metric] for metric in METRICS}, predictions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Only official NanoSciFact sanity task")
    parser.add_argument("--modes", nargs="+", choices=("official", "dense", "hybrid"), default=["official", "dense", "hybrid"])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/eval_runs/external")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/eval_runs/external/cache")
    parser.add_argument("--baseline-sha")
    parser.add_argument("--run-id")
    parser.add_argument("--task-limit", type=int, help="Explicit partial run: first N tasks in predefined order; report others as not run")
    args = parser.parse_args()
    if len(set(args.modes)) != len(args.modes):
        parser.error("Modes must be unique")
    if "dense" in args.modes and "official" not in args.modes:
        parser.error("Dense comparison requires the official baseline")
    if "hybrid" in args.modes and not {"official", "dense"}.issubset(args.modes):
        parser.error("Hybrid comparison requires official/dense parity first")
    if args.task_limit is not None and (args.task_limit <= 0 or args.smoke):
        parser.error("--task-limit must be positive and cannot be combined with --smoke")
    run_dir = args.output_dir / (args.run_id or datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + ("-smoke" if args.smoke else "-nanobeir"))
    run_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    logging.getLogger("mteb").setLevel(logging.ERROR)
    with benchmark_environment(args.cache_dir):
        import mteb

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            tasks = [mteb.get_task("NanoSciFactRetrieval")] if args.smoke else list(mteb.get_benchmark("NanoBEIR").tasks)
        report = {"benchmark": "NanoSciFact smoke" if args.smoke else "MTEB predefined NanoBEIR", "created_at": datetime.now(UTC).isoformat(), "config": capture_config(ROOT, modes=args.modes, tasks=[t.metadata.name for t in tasks], baseline_sha=args.baseline_sha, cache_root=args.cache_dir), "tasks": [], "duration_seconds": 0.0}
        selected = select_task_names(report["config"]["task_list"], args.task_limit)
        report["config"].update(task_limit=args.task_limit, selected_task_list=selected,
                                 scope="partial NanoBEIR" if len(selected) < len(tasks) else "complete task list")
        for task in tasks:
            name = task.metadata.name
            results = {} if name in selected else {
                mode: {"status": "not_run", "reason": f"Explicit task limit {args.task_limit}; outside first tasks in predefined MTEB order."}
                for mode in args.modes
            }
            report["tasks"].append({"task": name, "dataset": task.metadata.dataset, "license": task.metadata.license, "results": results})
        write_report(run_dir, report)
        encoder = None
        for task, row in zip(tasks[:len(selected)], report["tasks"], strict=False):
            name = task.metadata.name
            task_started = time.perf_counter()
            write_report(run_dir, report)
            print(f"{name}: loading official data", flush=True)
            try:
                task.load_data(num_proc=1)
                if set(task.dataset) != {"default"} or set(task.dataset["default"]) != {"train"}:
                    raise ValueError("NanoBEIR adapter requires the official default/train split.")
                data = task.dataset["default"]["train"]
                qrels = canonical_qrels(data["relevant_docs"])
                row.update(query_count=len(qrels), corpus_size=len(data["corpus"]))
                task_dir = run_dir / name
                task_dir.mkdir()
                if encoder is None:
                    encoder = DirectFastEmbedEncoder(args.cache_dir)
                    report["config"]["model_source_revision"] = model_source_revision(args.cache_dir)
                metrics, predictions = direct_evaluation(task, encoder, task_dir)
                ranked = {qid: [doc_id for doc_id, _ in sorted(scores.items(), key=lambda item: (item[1], item[0]), reverse=True)] for qid, scores in predictions.items()}
                # Independently verify our synthetic-tested metric implementation.
                checked = evaluate_rankings(qrels, ranked)
                if any(abs(metrics[metric] - checked[metric]) > 1e-4 for metric in METRICS):
                    raise ValueError(f"Official/helper metric mismatch: {metrics} vs {checked}")
                row["results"]["official"] = {"status": "completed", "metrics": metrics, "duration_seconds": time.perf_counter() - task_started}
                print(f"{name}: official {metrics}", flush=True)
                if "dense" in args.modes:
                    from app.services.embedding_provider import resolve_configured_embedding_provider
                    from app.core.config import get_settings

                    corpus = {str(record["id"]): record for record in data["corpus"]}
                    if len(corpus) != len(data["corpus"]):
                        raise ValueError("Duplicate official corpus IDs")
                    queries = {str(record["id"]): record["text"] for record in data["queries"]}
                    if not set(qrels).issubset(queries):
                        raise ValueError("Official judged query missing from query dataset")
                    if len(queries) != len(data["queries"]):
                        raise ValueError("Duplicate official query IDs")
                    queries = {qid: queries[qid] for qid in qrels}
                    comparison_started = time.perf_counter()
                    with purelink_index(corpus, resolve_configured_embedding_provider(get_settings())) as index:
                        dense = purelink_rankings(index, queries, mode="dense")
                        dense_metrics = evaluate_rankings(qrels, dense)
                        (task_dir / "dense-rankings.json").write_text(json.dumps({qid: ranking_scores(ids) for qid, ids in dense.items()}, indent=2) + "\n")
                        row["results"]["dense"] = {"status": "completed", "metrics": dense_metrics,
                                                  "duration_seconds": time.perf_counter() - comparison_started}
                        row["direct_dense_delta"] = {metric: dense_metrics[metric] - metrics[metric] for metric in METRICS}
                        # Fixed before observing benchmark results; stop rather than tune.
                        parity = all(abs(delta) <= 0.02 for delta in row["direct_dense_delta"].values())
                        row["dense_parity"] = {"passed": parity, "absolute_metric_tolerance": 0.02,
                                               "notes": "Official float32 matrix cosine vs production Python cosine; production case/whitespace normalization and tie ordering."}
                        print(f"{name}: dense {dense_metrics}; parity={parity}", flush=True)
                        if "hybrid" in args.modes:
                            if not parity:
                                row["results"]["hybrid"] = {"status": "blocked", "reason": "Direct/dense discrepancy exceeds 0.02; investigate before hybrid."}
                            else:
                                hybrid_started = time.perf_counter()
                                hybrid = purelink_rankings(index, queries, mode="hybrid")
                                hybrid_metrics = evaluate_rankings(qrels, hybrid)
                                (task_dir / "hybrid-rankings.json").write_text(json.dumps({qid: ranking_scores(ids) for qid, ids in hybrid.items()}, indent=2) + "\n")
                                row["results"]["hybrid"] = {"status": "completed", "metrics": hybrid_metrics,
                                                           "duration_seconds": time.perf_counter() - hybrid_started}
                                print(f"{name}: hybrid {hybrid_metrics}", flush=True)
            except Exception as exc:
                for mode in args.modes:
                    if mode not in row["results"]:
                        row["results"][mode] = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
                print(f"{name}: FAILED {type(exc).__name__}: {exc}", flush=True)
            row["duration_seconds"] = time.perf_counter() - task_started
            report["duration_seconds"] = time.perf_counter() - started
            write_report(run_dir, report)
    print(f"Report: {run_dir}", flush=True)
    if not report["aggregate"]["shared_completed_tasks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
