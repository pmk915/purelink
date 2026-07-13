from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base, load_all_models
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem
from app.services.document import list_documents_for_knowledge_base
from app.services.qa import (
    HeuristicAnswerGenerator,
    answer_question,
    extract_used_citation_ids,
)
from app.services.retrieval import RetrievalMode, RetrievalRequest, retrieve
from scripts.eval.rag_eval import (
    RagEvalCase,
    evaluate_retrieval_result,
    failed_case_result,
    load_cases,
)
from scripts.eval.rag_generalization import (
    build_run_id,
    build_run_metadata,
    category_counts,
    render_summary_markdown,
    results_payload,
    validate_corpus,
    write_sanitized_snapshot,
)
from scripts.eval.run_rag_eval_baseline import (
    _baseline_environment,
    _create_eval_user_and_kb,
    _ingest_sources,
)


def main() -> None:
    args = parse_args()
    created_at = datetime.now(UTC)
    run_id = args.run_id or build_run_id(
        mode=args.mode,
        chunk_strategy=args.chunk_strategy,
        created_at=created_at,
    )
    run_dir = args.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(args.cases)
    corpus_manifest = validate_corpus(args.corpus_dir, cases)
    source_paths = tuple(item["path"] for item in corpus_manifest)

    started = time.perf_counter()
    with TemporaryDirectory(prefix="purelink-rag-generalization-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        with _baseline_environment(
            chunk_strategy=args.chunk_strategy,
            upload_root=temp_dir / "uploads",
            vector_root=temp_dir / "vector_store",
            chunks_root=temp_dir / "chunks",
        ):
            results = asyncio.run(
                run_generalization_cases(
                    cases=cases,
                    source_paths=source_paths,
                    mode=args.mode,
                    root=temp_dir,
                )
            )
            settings = get_settings()
    duration_ms = int((time.perf_counter() - started) * 1000)

    run_metadata = build_run_metadata(
        run_id=run_id,
        created_at=created_at,
        case_file=args.cases,
        corpus_manifest=corpus_manifest,
        case_count=len(cases),
        chunk_strategy=args.chunk_strategy,
        requested_mode=args.mode,
        settings=settings,
        duration_ms=duration_ms,
    )
    run_payload = {
        **run_metadata,
        "case_category_counts": category_counts(cases),
    }
    results_json = results_payload(results)
    summary = render_summary_markdown(run_metadata=run_payload, results=results)

    (run_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "results.json").write_text(
        json.dumps(results_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(summary, encoding="utf-8")
    output_payload = {"run_dir": run_dir.as_posix(), **run_payload}
    if args.baseline_snapshot_dir is not None:
        write_sanitized_snapshot(
            snapshot_dir=args.baseline_snapshot_dir,
            run_payload=run_payload,
            results_json=results_json,
            summary_markdown=summary,
        )
        output_payload["baseline_snapshot_dir"] = args.baseline_snapshot_dir.as_posix()
    print(json.dumps(output_payload, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PureLink cross-domain RAG generalization eval.")
    parser.add_argument("--cases", type=Path, default=Path("tests/eval/rag_generalization_cases.jsonl"))
    parser.add_argument("--corpus-dir", type=Path, default=Path("tests/eval/corpus"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/eval_runs"))
    parser.add_argument("--baseline-snapshot-dir", type=Path)
    parser.add_argument("--mode", default=os.environ.get("EVAL_MODE", "auto"))
    parser.add_argument("--chunk-strategy", default=os.environ.get("EVAL_CHUNK_STRATEGY", "block_aware"))
    parser.add_argument("--run-id")
    return parser.parse_args()


async def run_generalization_cases(
    *,
    cases: list[RagEvalCase],
    source_paths: tuple[str, ...],
    mode: str,
    root: Path,
):
    load_all_models()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)
    try:
        with testing_session_local() as db:
            user, knowledge_base = _create_eval_user_and_kb(db, baseline_name="generalization")
            _ingest_sources(
                db,
                user=user,
                knowledge_base=knowledge_base,
                source_paths=source_paths,
                upload_root=root / "uploads",
                chunks_root=root / "chunks",
                vector_root=root / "vector_store",
                chunk_strategy=os.environ.get("CHUNK_STRATEGY", "block_aware"),
            )
            db.commit()
            documents = list_documents_for_knowledge_base(db, knowledge_base_id=knowledge_base.id)
            results = []
            for case in cases:
                eval_case = _case_for_temp_kb(case, knowledge_base_id=knowledge_base.id, user_id=user.id, mode=mode)
                case_started = time.perf_counter()
                try:
                    retrieval_started = time.perf_counter()
                    retrieval_result = await retrieve(
                        RetrievalRequest(
                            db=db,
                            documents=documents,
                            vector_root=root / "vector_store",
                            scope=KnowledgeBaseScope.PERSONAL,
                            knowledge_base_id=knowledge_base.id,
                            user_id=user.id,
                            query=case.question,
                            evidence_query=case.question,
                            mode=RetrievalMode(mode),
                            top_k=case.top_k,
                            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
                            enable_trace=True,
                            settings=get_settings(),
                        )
                    )
                    retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)
                    qa_result = answer_question(
                        db=db,
                        question=case.question,
                        retrieved_chunks=retrieval_result.metadata.get("retrieved_chunks", []),
                        retrieval_result=retrieval_result,
                        generator=HeuristicAnswerGenerator(),
                        settings=get_settings(),
                    )
                    retrieval_result.metadata.update(
                        {
                            "eval_answer_citation_count": len(qa_result.citations),
                            "eval_answer_marker_count": len(
                                extract_used_citation_ids(qa_result.answer)
                            ),
                        }
                    )
                    total_eval_latency_ms = int((time.perf_counter() - case_started) * 1000)
                    trace_item_count, initial_candidate_count = _load_trace_counts(
                        db,
                        trace_id=retrieval_result.trace_id,
                    )
                    results.append(
                        evaluate_retrieval_result(
                            eval_case,
                            retrieval_result,
                            trace_item_count=trace_item_count,
                            initial_candidate_count=initial_candidate_count,
                            latency_ms=retrieval_latency_ms,
                            retrieval_latency_ms=retrieval_latency_ms,
                            total_eval_latency_ms=total_eval_latency_ms,
                            retrieval_min_score=get_settings().retrieval_min_score,
                        )
                    )
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    results.append(failed_case_result(eval_case, error=f"{type(exc).__name__}: {exc}"))
            return results
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _case_for_temp_kb(case: RagEvalCase, *, knowledge_base_id: int, user_id: int, mode: str) -> RagEvalCase:
    return RagEvalCase(
        id=case.id,
        question=case.question,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        mode=mode,
        top_k=case.top_k,
        expected_doc_names=case.expected_doc_names,
        expected_doc_ids=case.expected_doc_ids,
        expected_keywords=case.expected_keywords,
        expected_citation_required=case.expected_citation_required,
        notes=case.notes,
        scope=KnowledgeBaseScope.PERSONAL.value,
        team_id=None,
        category=case.category,
        expected_mode=case.expected_mode,
        expected_evidence_phrases=case.expected_evidence_phrases,
        forbidden_evidence_phrases=case.forbidden_evidence_phrases,
        expected_answerable=case.expected_answerable,
    )


def _load_trace_counts(db, *, trace_id):  # noqa: ANN001
    if trace_id is None:
        return None, None
    trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == int(trace_id)))
    item_count = db.scalar(
        select(func.count(RetrievalTraceItem.id)).where(RetrievalTraceItem.trace_id == int(trace_id))
    )
    return int(item_count or 0), trace.initial_candidate_count if trace is not None else None


if __name__ == "__main__":
    main()
