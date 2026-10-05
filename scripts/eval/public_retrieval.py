"""Network-free helpers for external retrieval validation, separate from RAG eval."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
from typing import Mapping, Sequence

from app.core.config import get_settings

ENGLISH_MODEL = "BAAI/bge-small-en-v1.5"
MODEL_SOURCE = "Qdrant/bge-small-en-v1.5-onnx-Q"
METRICS = ("ndcg_at_10", "recall_at_10", "mrr_at_10", "recall_at_5")
REPRESENTATION = "nonempty official title + newline + official text; no added content; one document per chunk"


def select_task_names(task_names: Sequence[str], limit: int | None = None) -> list[str]:
    """Resource-limited runs keep predefined order, never select by scores."""
    if limit is not None and limit <= 0:
        raise ValueError("Task limit must be positive.")
    return list(task_names[:limit])


def corpus_text(record: Mapping[str, object]) -> str:
    title, text = record.get("title") or "", record.get("text") or ""
    if not isinstance(title, str) or not isinstance(text, str):
        raise ValueError("Corpus title/text must be strings.")
    return "\n".join(part for part in (title, text) if part)


def convert_corpus(corpus: Mapping[object, Mapping[str, object]]) -> dict[str, dict[str, str]]:
    converted = {}
    for doc_id, record in corpus.items():
        key = str(doc_id)
        if key in converted:
            raise ValueError(f"Duplicate canonical document ID: {key}")
        converted[key] = {"title": str(record.get("title") or ""), "text": corpus_text(record)}
    return converted


def canonical_qrels(qrels: Mapping[object, Mapping[object, object]]) -> dict[str, dict[str, float]]:
    result = {}
    for query_id, judgments in qrels.items():
        key = str(query_id)
        if key in result:
            raise ValueError("Duplicate canonical query ID.")
        result[key] = {}
        for doc_id, relevance in judgments.items():
            value = float(relevance)
            if not math.isfinite(value) or str(doc_id) in result[key]:
                raise ValueError("Invalid or duplicate relevance judgment.")
            result[key][str(doc_id)] = value
    return result


def ranking_scores(ranked_ids: Sequence[object], *, top_k: int = 10) -> dict[str, float]:
    """Rank-preserving scores avoid backend-specific tie handling; deduplicate first."""
    if top_k <= 0:
        raise ValueError("top_k must be positive.")
    unique = list(dict.fromkeys(str(doc_id) for doc_id in ranked_ids))[:top_k]
    return {doc_id: float(len(unique) - rank) for rank, doc_id in enumerate(unique)}


def evaluate_rankings(qrels, rankings) -> dict[str, float]:
    """TREC-compatible linear graded nDCG; unreturned relevant IDs remain in IDCG.

    All judged queries, including missing rankings, enter the macro denominator.
    Zero/negative judgments are not relevant. Missing/unjudged hits get zero gain.
    """
    qrels = canonical_qrels(qrels)
    rows = []
    for query_id, judgments in qrels.items():
        relevant = {doc_id: rel for doc_id, rel in judgments.items() if rel > 0}
        ranked = list(ranking_scores(rankings.get(query_id, [])))
        gains = [relevant.get(doc_id, 0.0) for doc_id in ranked[:10]]
        dcg = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(gains))
        ideal = sum(gain / math.log2(rank + 2) for rank, gain in enumerate(sorted(relevant.values(), reverse=True)[:10]))
        first = next((rank for rank, doc_id in enumerate(ranked[:10], 1) if doc_id in relevant), None)
        rows.append({
            "ndcg_at_10": dcg / ideal if ideal else 0.0,
            "recall_at_10": len(set(ranked[:10]) & relevant.keys()) / len(relevant) if relevant else 0.0,
            "mrr_at_10": 1.0 / first if first else 0.0,
            "recall_at_5": len(set(ranked[:5]) & relevant.keys()) / len(relevant) if relevant else 0.0,
        })
    return {metric: sum(row[metric] for row in rows) / len(rows) if rows else 0.0 for metric in METRICS}


def aggregate_results(tasks: list[dict], modes: Sequence[str]) -> dict:
    shared = [task for task in tasks if all(task.get("results", {}).get(mode, {}).get("status") == "completed" for mode in modes)]
    return {
        "shared_completed_tasks": [task["task"] for task in shared],
        "excluded_tasks": [task["task"] for task in tasks if task not in shared],
        "macro_mean": {
            mode: {metric: sum(task["results"][mode]["metrics"][metric] for task in shared) / len(shared) if shared else None for metric in METRICS}
            for mode in modes
        },
    }


def model_source_revision(cache_root: Path) -> str | None:
    reference = cache_root / "models" / ("models--" + MODEL_SOURCE.replace("/", "--")) / "refs/main"
    return reference.read_text().strip() if reference.is_file() else None


def capture_config(root: Path, *, modes: Sequence[str], tasks: Sequence[str], baseline_sha: str | None = None, cache_root: Path | None = None) -> dict:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    versions = {}
    for package in ("mteb", "fastembed", "onnxruntime", "torch", "datasets", "numpy", "pytrec-eval-terrier"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    settings = get_settings()
    return {
        "commit_sha": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
        "baseline_sha": baseline_sha, "python_version": platform.python_version(), "versions": versions,
        "embedding_provider": "fastembed", "embedding_model": ENGLISH_MODEL,
        "embedding_dimension": 384, "normalization": True, "retrieval_modes": list(modes), "top_k": 10,
        "reranker": {"enabled": False, "provider": "noop"}, "task_list": list(tasks),
        "document_representation": REPRESENTATION, "device": "cpu", "execution_provider": "CPUExecutionProvider",
        "model_source": MODEL_SOURCE, "model_source_revision": model_source_revision(cache_root or root / "data/eval_runs/external/cache"),
        "keyword_top_n": settings.keyword_retrieval_top_n, "keyword_min_score": settings.keyword_retrieval_min_score,
        "hybrid_implementation": "retrieve_hybrid_text_chunks (including inner lexical/metadata fusion); production weights unchanged",
    }


@contextmanager
def benchmark_environment(cache_root: Path):
    """Explicit English profile, scoped to this process; never read/write .env."""
    values = {
        "EMBEDDING_PROVIDER": "fastembed", "EMBEDDING_MODEL": ENGLISH_MODEL,
        "EMBEDDING_NORMALIZE": "true", "EMBEDDING_DIMENSION": "384",
        "EMBEDDING_MODEL_CACHE_DIR": str(cache_root / "models"),
        "HF_HOME": str(cache_root / "huggingface"),
        "HF_DATASETS_CACHE": str(cache_root / "huggingface" / "datasets"),
        "MTEB_CACHE": str(cache_root / "mteb"),
        "RERANKER_ENABLED": "false", "RERANKER_PROVIDER": "noop",
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@contextmanager
def purelink_index(corpus, provider):
    """One official document per chunk; production artifact + ephemeral chunk DB.

    No persisted users, KBs, processing jobs, or product ingestion. Only the chunk
    table is created; SQLite foreign-key enforcement is off in this isolated DB.
    """
    from sqlalchemy import create_engine, insert
    from sqlalchemy.orm import Session
    from app.db.base import load_all_models
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk
    from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, KnowledgeBaseScope
    from app.services.document_embedding import build_index_relative_path

    converted = convert_corpus(corpus)
    keys = sorted(converted)
    vectors = provider.embed_texts([converted[key]["text"] for key in keys])
    if len(vectors) != len(keys) or not vectors or len({len(vector) for vector in vectors}) != 1:
        raise ValueError("Invalid corpus embedding batch.")
    identity = {"embedding_provider": provider.provider_name, "embedding_model": provider.model,
                "embedding_dimension": len(vectors[0]), "embedding_normalize": provider.normalize}
    payload = {**identity, "embedding_scheme": provider.scheme, "documents": []}
    documents, rows, source_ids = [], [], {}
    for number, (key, vector) in enumerate(zip(keys, vectors, strict=True), 1):
        record = converted[key]
        chunk_key = f"benchmark:{number}"
        source_ids[number] = key
        documents.append(Document(id=number, knowledge_base_id=1, original_filename=record["title"],
                                  review_status=DocumentReviewStatus.NOT_REQUIRED, processing_status=DocumentProcessingStatus.INDEXED))
        rows.append({"id": number, "document_id": number, "chunk_index": 0, "chunk_key": chunk_key,
                     "chunk_text": record["text"], "metadata_json": "{}"})
        payload["documents"].append({**identity, "document_id": number, "document_name": record["title"],
                                    "chunks": [{"chunk_db_id": number, "chunk_id": chunk_key, "text": record["text"],
                                                "vector": vector, "metadata": {}}]})
    load_all_models()
    engine = create_engine("sqlite://")
    try:
        DocumentChunk.__table__.create(engine)
        with TemporaryDirectory(prefix="purelink-public-index-") as temporary, Session(engine) as db:
            vector_root = Path(temporary)
            path = vector_root / build_index_relative_path(scope=KnowledgeBaseScope.PERSONAL, knowledge_base_id=1)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            db.execute(insert(DocumentChunk), rows)
            db.commit()
            yield db, documents, vector_root, source_ids
    finally:
        engine.dispose()


def purelink_rankings(index, queries, *, mode: str, top_k: int = 10) -> dict[str, list[str]]:
    from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
    from app.services.document_embedding import search_index
    from app.services.retrieval.chunk_retriever import preprocess_retrieval_query
    from app.services.retrieval.hybrid_text_retriever import retrieve_hybrid_text_chunks

    if mode not in {"dense", "hybrid"}:
        raise ValueError("Public adapter supports dense/hybrid only.")
    db, documents, vector_root, source_ids = index
    common = dict(vector_root=vector_root, scope=KnowledgeBaseScope.PERSONAL, knowledge_base_id=1, top_k=top_k)
    result = {}
    for query_id, text in queries.items():
        if mode == "dense":
            # Match the production vector branch's whitespace/case preprocessing.
            chunks = search_index(**common, query=preprocess_retrieval_query(text).normalized_text,
                                  allowed_document_ids=set(source_ids), document_lookup={doc.id: doc for doc in documents})
        else:
            chunks, metadata = retrieve_hybrid_text_chunks(**common, db=db, documents=documents, query=text,
                                                          required_review_status=DocumentReviewStatus.NOT_REQUIRED)
            if metadata.keyword_failed:
                raise RuntimeError("Production keyword branch failed; do not label fallback dense as hybrid.")
        result[str(query_id)] = list(ranking_scores([source_ids[chunk.document_id] for chunk in chunks], top_k=top_k))
    return result
