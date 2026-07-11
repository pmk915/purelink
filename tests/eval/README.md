# PureLink RAG Eval

This directory contains a lightweight, deterministic RAG evaluation harness.

It does not use LLM-as-judge, external APIs, or heavy evaluation frameworks. It checks service-level retrieval outputs with simple metrics:

- retrieval hit
- citation hit
- keyword coverage
- reranker usage
- trace availability
- expected/forbidden evidence hit
- evidence precision
- router accuracy
- no-answer answerability accuracy

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
make eval-rag EVAL_CASES=tests/eval/purelink_rag_cases.jsonl
```

## Generalization Eval

For a deterministic cross-domain retrieval baseline that does not depend on
local KB ids, run:

```bash
make eval-rag-generalization
```

This command builds a temporary in-memory eval KB from the curated corpus in
`tests/eval/corpus/`, indexes it with the configured chunk strategy, runs the
50 JSONL cases in `tests/eval/rag_generalization_cases.jsonl`, and writes:

```text
data/eval_runs/<run-id>/run.json
data/eval_runs/<run-id>/results.json
data/eval_runs/<run-id>/summary.md
```

The generalization corpus covers entity definition, entity attribute, entity
reason, entity relation, technical, overview, and no-answer cases. It uses
phrase/document checks only; it does not use LLM-as-judge.

To generate a sanitized local snapshot preview:

```bash
make eval-rag-generalization \
  GENERALIZATION_BASELINE_SNAPSHOT_DIR=tests/eval/baselines/generalization-auto-block-aware
```

The snapshot removes live trace ids, temporary database ids, absolute local
paths, and secret-like configuration. Rerun on a clean commit before committing
an official baseline snapshot.

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

## Interview Baseline Eval

For an interview-ready local baseline:

1. Create a local PureLink KB.
2. Upload these docs:
   - `README.md`
   - `docs/retrieval-and-citations.md`
   - `docs/architecture/rag-v2-architecture.md`
   - `docs/roadmap/M2-model-provider-standardization.md`
   - `docs/roadmap/M3-optional-reranker-integration.md`
   - `docs/roadmap/M4-index-version-and-rebuild-readiness.md`
   - `docs/roadmap/M5-retrieval-trace.md`
   - `docs/roadmap/M6-document-block-schema-parser-routing.md`
   - `docs/roadmap/M7-lightweight-graphrag-and-rag-v2-closure.md`
   - `docs/roadmap/M8-lightweight-rag-evaluation.md`
3. Wait until documents are indexed.
4. Copy the template:

```bash
cp tests/eval/purelink_rag_interview_cases.template.jsonl tests/eval/purelink_rag_interview_cases.local.jsonl
```

5. Edit the local file and replace:
   - `knowledge_base_id`
   - `user_id`
   - `expected_doc_names`
6. Run:

```bash
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

7. Save a named baseline report:

```bash
make eval-rag \
  EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl \
  EVAL_OUTPUT=tests/eval/reports/rag-v2-baseline.json
```

Local cases and generated reports depend on local KB IDs and should not be committed unless intentionally curated.

## Interpret Results

- `retrieval_hit`: final selected evidence came from an expected document. It is `null` when the case has no expected document.
- `citation_hit`: final selected citation-ready evidence came from an expected document. It is `null` when citation is not required, and citation evidence must include both citation unit and source locator metadata.
- `keyword_coverage`: expected keyword substring matches in `RetrievalResult.context_text`.
- `used_reranker`: whether retrieval used the reranker for that case.
- `trace_available`: whether `RetrievalResult.trace_id` was populated.
- Generalization summaries show `passed / applicable (percentage)` and skip `null` values from denominators.
- Evidence-gate answerability means final evidence is present and reaches `RETRIEVAL_MIN_SCORE`; it is not semantic QA accuracy.
- Final evidence metrics use `RetrievalResult.evidences`, not raw `initial_chunks` or intermediate `context_chunks`.

This harness is intended for local/manual RAG quality checks and regression comparison. Metric unit tests live in `tests/eval/test_rag_eval_metrics.py` and are safe for the default test suite.

## Compare Chunk Strategies

To compare `fixed` and `block_aware` chunking:

1. Set `CHUNK_STRATEGY=fixed`.
2. Reindex the evaluation documents.
3. Run eval and save the report.
4. Set `CHUNK_STRATEGY=block_aware`.
5. Reindex the same documents.
6. Run eval and save the second report.
7. Compare retrieval hit, citation hit, keyword coverage, and top-1/top-3 document hit.

Do not assume block-aware chunking improves every query. Use the reports to compare behavior for your local corpus.
