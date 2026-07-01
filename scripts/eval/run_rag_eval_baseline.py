from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import time
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import BASE_DIR, get_settings
from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
from app.models.knowledge_base import KnowledgeBase
from app.models.retrieval_trace import RetrievalTrace, RetrievalTraceItem
from app.models.user import User
from app.providers.embedding.factory import reset_embedding_provider_cache
from app.services.document import list_documents_for_knowledge_base
from app.services.document_indexing import build_document_index
from app.services.document_processing import process_document
from app.services.retrieval import RetrievalMode, RetrievalRequest, retrieve
from scripts.eval.rag_eval import RagEvalCase, evaluate_retrieval_result, failed_case_result
from scripts.eval.rag_eval_baseline import (
    baseline_summary_to_dict,
    build_baseline_payload,
    default_baselines,
    load_baseline_cases,
    render_summary_markdown,
    source_paths_for_cases,
    summarize_baseline_results,
    validate_summary_markdown,
)


def main() -> None:
    args = parse_args()
    cases = load_baseline_cases(args.cases)
    source_paths = source_paths_for_cases(cases)
    _validate_source_paths(source_paths)

    baseline_summaries: list[dict[str, object]] = []
    with TemporaryDirectory(prefix="purelink-rag-eval-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        for baseline in default_baselines():
            baseline_root = temp_dir / baseline.name
            baseline_root.mkdir(parents=True, exist_ok=True)
            with _baseline_environment(
                chunk_strategy=baseline.chunk_strategy,
                upload_root=baseline_root / "uploads",
                vector_root=baseline_root / "vector_store",
                chunks_root=baseline_root / "chunks",
            ):
                summary = asyncio.run(
                    _run_baseline(
                        baseline_name=baseline.name,
                        chunk_strategy=baseline.chunk_strategy,
                        mode=baseline.mode,
                        cases=cases,
                        source_paths=source_paths,
                        root=baseline_root,
                    )
                )
            baseline_summaries.append(
                baseline_summary_to_dict(
                    baseline=baseline,
                    summary=summary,
                )
            )

    payload = build_baseline_payload(
        cases_path=args.cases,
        cases=cases,
        source_paths=source_paths,
        baseline_summaries=baseline_summaries,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown = render_summary_markdown(payload)
    validate_summary_markdown(markdown)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(markdown, encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PureLink M18 real RAG eval baseline.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("docs/interview/rag-eval-cases.json"),
        help="Path to JSON or JSONL eval cases.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/interview/rag-eval-baseline-results.json"),
        help="Path to write raw JSON baseline results.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("docs/interview/rag-eval-baseline-summary.md"),
        help="Path to write interview-ready Markdown summary.",
    )
    return parser.parse_args()


async def _run_baseline(
    *,
    baseline_name: str,
    chunk_strategy: str,
    mode: str,
    cases,
    source_paths: tuple[str, ...],
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
            user, knowledge_base = _create_eval_user_and_kb(db, baseline_name=baseline_name)
            _ingest_sources(
                db,
                user=user,
                knowledge_base=knowledge_base,
                source_paths=source_paths,
                upload_root=root / "uploads",
                chunks_root=root / "chunks",
                vector_root=root / "vector_store",
                chunk_strategy=chunk_strategy,
            )
            db.commit()
            results = []
            for case in cases:
                eval_case = RagEvalCase(
                    id=case.id,
                    question=case.question,
                    knowledge_base_id=knowledge_base.id,
                    user_id=user.id,
                    mode=mode,
                    top_k=case.top_k,
                    expected_doc_names=(case.expected_source_hint,),
                    expected_keywords=case.expected_answer_contains,
                    expected_citation_required=True,
                    notes=case.notes,
                    scope=KnowledgeBaseScope.PERSONAL.value,
                )
                started = time.perf_counter()
                try:
                    documents = list_documents_for_knowledge_base(
                        db,
                        knowledge_base_id=knowledge_base.id,
                    )
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
                    latency_ms = int((time.perf_counter() - started) * 1000)
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
                            latency_ms=latency_ms,
                        )
                    )
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    results.append(failed_case_result(eval_case, error=f"{type(exc).__name__}: {exc}"))
            return summarize_baseline_results(results)
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_eval_user_and_kb(db: Session, *, baseline_name: str) -> tuple[User, KnowledgeBase]:
    user = User(
        email=f"rag-eval-{baseline_name}@example.com",
        username=f"rag-eval-{baseline_name}",
        hashed_password="not-used",
        is_active=True,
    )
    db.add(user)
    db.flush()
    knowledge_base = KnowledgeBase(
        name=f"RAG Eval {baseline_name}",
        description="Temporary M18 RAG eval baseline KB.",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()
    return user, knowledge_base


def _ingest_sources(
    db: Session,
    *,
    user: User,
    knowledge_base: KnowledgeBase,
    source_paths: tuple[str, ...],
    upload_root: Path,
    chunks_root: Path,
    vector_root: Path,
    chunk_strategy: str,
) -> None:
    upload_root.mkdir(parents=True, exist_ok=True)
    chunks_root.mkdir(parents=True, exist_ok=True)
    vector_root.mkdir(parents=True, exist_ok=True)

    for index, source_path in enumerate(source_paths, start=1):
        source = ROOT / source_path
        storage_path = Path("eval") / chunk_strategy / f"{index:02d}-{source.name}"
        destination = upload_root / storage_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        raw_bytes = source.read_bytes()
        document = Document(
            knowledge_base_id=knowledge_base.id,
            owner_id=user.id,
            submitted_by=user.id,
            filename=destination.name,
            original_filename=source_path,
            file_type=_file_type_for_path(source),
            file_size=len(raw_bytes),
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            storage_path=storage_path.as_posix(),
            review_status=DocumentReviewStatus.NOT_REQUIRED,
            processing_status=DocumentProcessingStatus.UPLOADED,
        )
        db.add(document)
        db.flush()
        process_document(db, document=document, upload_root=upload_root)
        build_document_index(
            db,
            document=document,
            chunks_root=chunks_root,
            vector_root=vector_root,
        )
        db.flush()


def _load_trace_counts(db: Session, *, trace_id: int | str | None) -> tuple[int | None, int | None]:
    if trace_id is None:
        return None, None
    trace = db.scalar(select(RetrievalTrace).where(RetrievalTrace.id == int(trace_id)))
    item_count = db.scalar(
        select(func.count(RetrievalTraceItem.id)).where(RetrievalTraceItem.trace_id == int(trace_id))
    )
    return int(item_count or 0), trace.initial_candidate_count if trace is not None else None


@contextmanager
def _baseline_environment(
    *,
    chunk_strategy: str,
    upload_root: Path,
    vector_root: Path,
    chunks_root: Path,
) -> Iterator[None]:
    overrides = {
        "CHUNK_STRATEGY": chunk_strategy,
        "UPLOAD_DIR": upload_root.as_posix(),
        "VECTOR_STORE_DIR": vector_root.as_posix(),
        "CHUNKS_DIR": chunks_root.as_posix(),
        "EMBEDDING_PROVIDER": "local_hashed_bow",
        "EMBEDDING_MODEL": "hashed_bow_v1",
        "EMBEDDING_DIMENSION": "128",
        "RERANKER_ENABLED": "false",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    _reset_settings_caches()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _reset_settings_caches()


def _reset_settings_caches() -> None:
    get_settings.cache_clear()
    reset_embedding_provider_cache()


def _validate_source_paths(source_paths: tuple[str, ...]) -> None:
    missing = [
        path
        for path in source_paths
        if not (ROOT / path).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"Eval source docs are missing: {', '.join(missing)}")


def _file_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


if __name__ == "__main__":
    main()
