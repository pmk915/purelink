# PureLink RAG Eval

This directory contains a lightweight, deterministic RAG evaluation harness.

It does not use LLM-as-judge, external APIs, or heavy evaluation frameworks. It checks service-level retrieval outputs with simple metrics:

- retrieval hit
- citation hit
- keyword coverage
- reranker usage
- trace availability

## Prepare Cases

Edit `tests/eval/purelink_rag_cases.jsonl`.

The included case is a template. Update these fields to match your local database:

- `knowledge_base_id`
- `user_id`
- `expected_doc_names`
- `expected_keywords`

Each line is one JSON object.

## Run

```bash
.venv/bin/python scripts/eval/run_rag_eval.py \
  --cases tests/eval/purelink_rag_cases.jsonl \
  --output tests/eval/reports/latest.json
```

Optional overrides:

```bash
.venv/bin/python scripts/eval/run_rag_eval.py --mode chunk_only --top-k 8
.venv/bin/python scripts/eval/run_rag_eval.py --disable-trace
```

## RAG v2 Baseline Evaluation

To capture a local RAG v2 baseline:

1. Upload known PureLink project docs or sample KB docs.
2. Edit `tests/eval/purelink_rag_cases.jsonl`.
3. Fill `knowledge_base_id`, `user_id`, `expected_doc_names`, and `expected_keywords`.
4. Run:

```bash
make eval-rag
```

5. Save the report as:

```text
tests/eval/reports/rag-v2-baseline.json
```

Baseline reports are local artifacts when they depend on local KB IDs and uploaded documents.

To compare retrieval modes, run the same cases with:

```bash
.venv/bin/python scripts/eval/run_rag_eval.py --mode chunk_only
.venv/bin/python scripts/eval/run_rag_eval.py --mode graph_vector_mix
```

## Interpret Results

- `retrieval_hit`: final selected evidence came from an expected document.
- `citation_hit`: final selected citation-ready evidence came from an expected document.
- `keyword_coverage`: expected keyword substring matches in `RetrievalResult.context_text`.
- `used_reranker`: whether retrieval used the reranker for that case.
- `trace_available`: whether `RetrievalResult.trace_id` was populated.

This harness is intended for local/manual RAG quality checks and regression comparison. Metric unit tests live in `tests/eval/test_rag_eval_metrics.py` and are safe for the default test suite.
