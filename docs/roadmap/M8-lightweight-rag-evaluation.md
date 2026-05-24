# PureLink M8 Upgrade Plan: Lightweight RAG Evaluation Harness

## Goal

M8 adds a lightweight, deterministic RAG evaluation harness. The goal is to compare retrieval quality across fixed questions without external APIs, LLM-as-judge, or heavy evaluation frameworks.

## Scope

- Define JSONL evaluation cases.
- Run service-level retrieval against a local PureLink database.
- Calculate deterministic metrics:
  - retrieval hit
  - citation hit
  - keyword coverage
  - reranker usage
  - trace availability
- Write JSON reports for local/manual evaluation.
- Keep production retrieval behavior unchanged.

## Non-goals

- No RAGAS.
- No LLM-as-judge.
- No semantic answer grading.
- No GraphRAG or DocumentBlock schema.
- No frontend UI.
- No required external APIs or large models.
- No live-data eval in default tests.

## Case Format

Evaluation cases live in `tests/eval/purelink_rag_cases.jsonl`.

Each line is one JSON object with fields such as:

- `id`
- `question`
- `knowledge_base_id`
- `user_id`
- `mode`
- `top_k`
- `expected_doc_names`
- `expected_doc_ids`
- `expected_keywords`
- `expected_citation_required`
- `notes`

The sample cases are templates. Local evaluation requires updating `knowledge_base_id`, `user_id`, and expected document names to match the local database.

## Runner

Run:

```bash
.venv/bin/python scripts/eval/run_rag_eval.py \
  --cases tests/eval/purelink_rag_cases.jsonl \
  --output tests/eval/reports/latest.json
```

The runner uses the service layer directly and returns a JSON report. It can record `RetrievalResult.trace_id` when trace is enabled.

## Future Work

M8 prepares PureLink for:

- comparing reranker on/off
- comparing retrieval modes
- evaluating future GraphRAG
- detecting RAG regressions
- interview demos that show retrieval, trace, and evaluation as one loop
