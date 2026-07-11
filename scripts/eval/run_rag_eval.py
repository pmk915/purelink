from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app.core.config import BASE_DIR, get_settings
from app.db.session import SessionLocal
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem
from app.services.document import list_documents_for_knowledge_base
from app.services.document_embedding import resolve_vector_store_root
from app.services.retrieval import RetrievalMode, RetrievalRequest, retrieve
from scripts.eval.rag_eval import (
    RagEvalCase,
    evaluate_retrieval_result,
    failed_case_result,
    load_cases,
    summarize_results,
    summary_to_dict,
)


def main() -> None:
    args = parse_args()
    cases = load_cases(args.cases)
    if args.mode:
        cases = [
            _override_case(case, mode=args.mode)
            for case in cases
        ]
    if args.top_k is not None:
        cases = [
            _override_case(case, top_k=args.top_k)
            for case in cases
        ]

    summary = asyncio.run(run_cases(cases, disable_trace=args.disable_trace))
    payload = summary_to_dict(summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lightweight PureLink RAG evaluation cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("tests/eval/purelink_rag_cases.jsonl"),
        help="Path to JSONL eval cases.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/eval/reports/latest.json"),
        help="Path to write JSON report.",
    )
    parser.add_argument(
        "--mode",
        choices=[item.value for item in RetrievalMode],
        help="Override retrieval mode for all cases.",
    )
    parser.add_argument("--top-k", type=int, help="Override top_k for all cases.")
    parser.add_argument("--disable-trace", action="store_true", help="Disable retrieval trace during evaluation.")
    return parser.parse_args()


async def run_cases(cases: list[RagEvalCase], *, disable_trace: bool):
    settings = get_settings()
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    results = []

    with SessionLocal() as db:
        for case in cases:
            try:
                knowledge_base = db.scalar(
                    select(KnowledgeBase).where(KnowledgeBase.id == case.knowledge_base_id)
                )
                if knowledge_base is None:
                    raise ValueError(f"Knowledge base not found: {case.knowledge_base_id}")

                documents = list_documents_for_knowledge_base(
                    db,
                    knowledge_base_id=knowledge_base.id,
                )
                scope = _resolve_scope(case, knowledge_base)
                required_review_status = (
                    DocumentReviewStatus.APPROVED
                    if scope == KnowledgeBaseScope.TEAM
                    else DocumentReviewStatus.NOT_REQUIRED
                )
                retrieval_result = await retrieve(
                    RetrievalRequest(
                        db=db,
                        documents=documents,
                        vector_root=vector_root,
                        scope=scope,
                        knowledge_base_id=knowledge_base.id,
                        user_id=case.user_id,
                        team_id=case.team_id if case.team_id is not None else knowledge_base.team_id,
                        query=case.question,
                        evidence_query=case.question,
                        mode=RetrievalMode(case.mode),
                        top_k=case.top_k,
                        required_review_status=required_review_status,
                        enable_trace=not disable_trace,
                    )
                )
                trace_item_count, initial_candidate_count = _load_trace_counts(
                    db,
                    trace_id=retrieval_result.trace_id,
                )
                results.append(
                    evaluate_retrieval_result(
                        case,
                        retrieval_result,
                        trace_item_count=trace_item_count,
                        initial_candidate_count=initial_candidate_count,
                    )
                )
                db.commit()
            except Exception as exc:
                db.rollback()
                results.append(failed_case_result(case, error=f"{type(exc).__name__}: {exc}"))

    return summarize_results(results)


def _load_trace_counts(db, *, trace_id):  # noqa: ANN001
    if trace_id is None:
        return None, None
    trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == int(trace_id)))
    item_count = db.scalar(
        select(func.count(RetrievalTraceItem.id)).where(RetrievalTraceItem.trace_id == int(trace_id))
    )
    return int(item_count or 0), trace.initial_candidate_count if trace is not None else None


def _resolve_scope(case: RagEvalCase, knowledge_base: KnowledgeBase) -> KnowledgeBaseScope:
    if case.scope:
        return KnowledgeBaseScope(case.scope)
    return knowledge_base.scope


def _override_case(
    case: RagEvalCase,
    *,
    mode: str | None = None,
    top_k: int | None = None,
) -> RagEvalCase:
    return RagEvalCase(
        id=case.id,
        question=case.question,
        knowledge_base_id=case.knowledge_base_id,
        user_id=case.user_id,
        mode=mode or case.mode,
        top_k=top_k if top_k is not None else case.top_k,
        expected_doc_names=case.expected_doc_names,
        expected_doc_ids=case.expected_doc_ids,
        expected_keywords=case.expected_keywords,
        expected_citation_required=case.expected_citation_required,
        notes=case.notes,
        scope=case.scope,
        team_id=case.team_id,
        category=case.category,
        expected_mode=case.expected_mode,
        expected_evidence_phrases=case.expected_evidence_phrases,
        forbidden_evidence_phrases=case.forbidden_evidence_phrases,
        expected_answerable=case.expected_answerable,
    )


if __name__ == "__main__":
    main()
