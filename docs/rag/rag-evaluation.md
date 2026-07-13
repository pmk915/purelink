# RAG Evaluation

PureLink includes a lightweight JSONL evaluation harness.

Runner:

```bash
make eval-rag
```

Cross-domain generalization baseline:

```bash
make eval-rag-generalization
```

Independent generalization holdout:

```bash
make eval-rag-generalization-holdout
```

Custom cases:

```bash
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

## Case Format

Each JSONL line includes:

- `id`
- `question`
- `knowledge_base_id`
- `user_id`
- `mode`
- `top_k`
- `expected_doc_names`
- `expected_keywords`
- `expected_citation_required`

The generalization case file also supports optional fields:

- `category`: one of `entity_definition`, `entity_attribute`, `entity_reason`, `entity_relation`, `technical`, `overview`, or `no_answer`.
- `expected_mode`: expected selected mode for `mode=auto` cases.
- `expected_evidence_phrases`: phrases that should appear in final evidence.
- `forbidden_evidence_phrases`: phrases that should not appear in final evidence.
- `expected_answerable`: deterministic evidence-gate answerability expectation.
- `notes`: free-form operator notes.

## Metrics

- `retrieval_hit`: expected document appears in final evidence. Applicable only when `expected_doc_names` or `expected_doc_ids` is present.
- `citation_hit`: citation-ready evidence appears from expected document. Applicable only when `expected_citation_required=true`; citation evidence must include both `citation_unit_id` and `source_locator`.
- `keyword_coverage`: expected keyword substring coverage in context.
- `top_1_doc_hit` / `top_3_doc_hit`: ranking quality indicators.
- `used_reranker`: whether reranker changed the pipeline.
- `trace_available`: whether retrieval produced a trace id.
- `expected_evidence_hit`: final evidence from an expected document contains an expected evidence phrase. Applicable only when `expected_evidence_phrases` is non-empty.
- `forbidden_evidence_hit`: final evidence contains a forbidden phrase. Applicable only when `forbidden_evidence_phrases` is non-empty.
- `irrelevant_evidence_count`: explicit forbidden evidence plus evidence from unexpected documents.
- `unknown_evidence_count`: evidence that cannot be judged by phrase/doc rules.
- `evidence_precision`: relevant / (relevant + irrelevant), excluding unknown evidence.
- `router_accuracy`: selected mode matches `expected_mode` for `auto` cases. Applicable only when the requested mode is `auto` and `expected_mode` is present.
- `answerability_accuracy`: production Evidence Support Gate answerability matches `expected_answerable`. The gate is deterministic and uses query-type mandatory checks such as requested attribute coverage, relation support, exact technical identifier coverage, and reason/definition signals.
- `evidence_support_score`, `evidence_support_reason`, `evidence_support_query_type`, and `evidence_support_signals`: debugging fields emitted by the production support evaluator.
- `retrieval_latency_ms` and `total_eval_latency_ms`: in-process retrieval timing values.
- `expected_document_in_raw_candidates` / `expected_evidence_in_raw_candidates`: whether the retriever returned the expected document and phrase before context selection.
- `expected_document_in_final_context` / `expected_evidence_in_final_context`: whether expected material survived context selection.
- `expected_document_in_final_selection` / `expected_evidence_in_final_selection`: whether expected material reached canonical final evidence.
- `failure_stage`: the earliest diagnosable loss point. Values include `retrieval_document_miss`, `raw_candidate_miss`, `final_context_miss`, `evidence_selection_miss`, `support_gate_miss`, `expected_phrase_format_mismatch`, `genuine_no_answer`, and `success`.

The harness is deterministic and does not use LLM-as-judge. The support score is
not a semantic correctness score; it explains why the rule-based production gate
allowed or rejected the final evidence.

The canonical final evidence source is `RetrievalResult.evidences`. Retrieval metadata such as `initial_chunks`, `context_chunks`, and `evidence_units` is useful for debugging, but summary metrics do not treat raw chunks as final citation evidence. When the reranker is enabled, `RetrievalResult.evidences` contains the aligned final evidence.

Expected phrase checks normalize presentation-only differences: Markdown
backticks and emphasis, repeated whitespace, case, quotes, Unicode punctuation,
and terminal punctuation. They preserve numbers, underscores, hyphens, path
separators, API paths, and CLI flags. For example, formatted and unformatted
`CHUNK_STRATEGY` are equivalent, while `docker compose down` and
`docker compose down -v` are not.

Summary tables show `passed / applicable (percentage)`. `null` or non-applicable metrics are skipped from the denominator, so no-answer cases do not dilute ordinary retrieval/citation rates.

## Generalization Corpus

`tests/eval/corpus/` contains nine small Markdown-like `.txt` documents covering Python classes, FastAPI dependencies, PostgreSQL concurrency, Alice in Wonderland characters, synthetic team roles, synthetic device catalog data, employee policy no-answer cases, PureLink retrieval, and PureLink document processing.

The external-source documents are concise paraphrases for deterministic local evaluation. The runner does not fetch network resources at runtime. The corpus is intentionally small; it is designed to reveal retrieval and evidence-selection regressions, not to prove production quality.

Run output is written under `data/eval_runs/<run-id>/`:

- `run.json`: run id, commit, dirty worktree flag, corpus manifest, config, model identity, and duration.
- `results.json`: per-case selected mode, router reason, final evidence units, evidence metrics, answerability metrics, trace id, latency, and failure reasons.
- `summary.md`: run configuration, overall metrics, category/mode breakdowns, no-answer results, latency summary, failed cases, and known limitations.

The generated reports should be interpreted as phrase/doc based approximations. Latency is useful only for comparison on the same machine and configuration.

The committed 50-case generalization set is a deterministic regression suite.
The independent holdout uses `tests/eval/holdout_corpus/` and
`tests/eval/rag_generalization_holdout_cases.jsonl`; it must remain separate
from the production-rule tuning loop. A fixture whose corpus does not contain
the requested fact should be modeled as no-answer and documented in case
notes, rather than counted as an answerable retrieval failure.

To write a sanitized local preview that can later become a committed baseline snapshot, use:

```bash
make eval-rag-generalization \
  GENERALIZATION_BASELINE_SNAPSHOT_DIR=tests/eval/baselines/generalization-auto-block-aware
```

The snapshot removes live trace ids, temporary database ids, absolute local paths, and secret-like configuration. Do not commit a dirty-worktree snapshot as the official baseline; rerun on a clean commit first.

Supported modes include:

- `chunk_only`
- `overview`
- `graph_vector_mix`
- `hybrid_text`

Use `hybrid_text` cases for keyword-heavy questions about API paths, config keys, file paths, commands, migration ids, or error codes.

## Comparing Chunk Strategies

To compare fixed and block-aware chunking:

1. Set `CHUNK_STRATEGY=fixed`.
2. Reindex the target documents.
3. Run eval and save the report.
4. Set `CHUNK_STRATEGY=block_aware`.
5. Reindex the same documents.
6. Run eval again.
7. Compare `retrieval_hit`, `citation_hit`, `keyword_coverage`, and `top_1_doc_hit` / `top_3_doc_hit`.

Block-aware chunking should be evaluated empirically. It preserves document structure better, but it is not expected to improve every case.

## Comparing Retrieval Modes

The same JSONL case set can be run with different modes to compare recall behavior:

1. Run with `mode=chunk_only`.
2. Run with `mode=hybrid_text`.
3. Compare `retrieval_hit`, `citation_hit`, `keyword_coverage`, and top-k document hits.

`hybrid_text` is expected to help exact technical queries. It should not be assumed to improve every semantic question.

## Adding a Generalization Case

1. Add or edit a small corpus document under `tests/eval/corpus/`.
2. Add one JSONL object to `tests/eval/rag_generalization_cases.jsonl`.
3. Include `expected_doc_names`, `expected_evidence_phrases`, and `forbidden_evidence_phrases` when the answer can be checked by phrases.
4. Use `expected_answerable=false` only when the answer is intentionally absent from the corpus.
5. Run `make eval-rag-generalization` and review failed cases instead of deleting them.
