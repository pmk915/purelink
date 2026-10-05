# RAG Evaluation

PureLink includes a lightweight JSONL evaluation harness. The only current official interview regression suite is the 50-case generalization set; the earlier 20-case repository-doc comparison is retained as historical material and is not a current result.

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

Separate deterministic format-coverage slice (24 cases, eight generated local documents):

```bash
make eval-rag-format
```

This reuses the generalization runner and current production ingestion/index/retrieval/QA path. It supplements the official 50-case suite and independent holdout. It does not replace either suite or change retrieval settings. See the [M2 measured baseline](format-benchmark-baseline.md).

Default Runtime evaluation over the same 50 cases:

```bash
make eval-rag-runtime
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
- `document_format`: optional `txt`, `markdown`, `docx`, or `pdf` label for format aggregation.
- `expected_page_numbers`: optional list of positive, one-based physical page numbers for provenance checks.

Categories are descriptive labels; the format slice adds `factual_lookup`, `section_scoped`, `distractor_sensitive`, and `structured_fact`. Existing cases need no schema migration.

## Metrics

- `retrieval_hit`: expected document appears in final evidence. Applicable only when `expected_doc_names` or `expected_doc_ids` is present.
- `citation_hit`: citation-ready evidence appears from expected document. Applicable only when `expected_citation_required=true`; citation evidence must include both `citation_unit_id` and `source_locator`.
- `keyword_coverage`: expected keyword substring coverage in context.
- `top_1_doc_hit` / `top_3_doc_hit`: legacy hits in the first one/three **final evidence positions**, without document deduplication. Their definitions are preserved; they are not the new document Recall@K.
- `document_recall_at_1` / `document_recall_at_3` / `document_recall_at_5`: distinct expected documents in the first K distinct ranked retrieved documents divided by the number of distinct expected documents.
- `document_mrr`: reciprocal rank of the first expected document; zero for a miss. The aggregate is the mean over applicable cases.
- `used_reranker`: whether reranker changed the pipeline.
- `trace_available`: whether retrieval produced a trace id.
- `expected_evidence_hit`: final evidence from an expected document contains an expected evidence phrase. Applicable only when `expected_evidence_phrases` is non-empty.
- `evidence_recall`: distinct normalized expected phrases present in canonical final evidence from expected documents divided by the number of distinct nonempty normalized expected phrases. Each phrase counts once even if multiple evidence units contain it; with no expected document restriction, all final evidence is eligible. Cases without usable expected phrases are non-applicable.
- `forbidden_evidence_hit`: final evidence contains a forbidden phrase. Applicable only when `forbidden_evidence_phrases` is non-empty.
- `irrelevant_evidence_count`: explicit forbidden evidence plus evidence from unexpected documents.
- `unknown_evidence_count`: evidence that cannot be judged by phrase/doc rules.
- `evidence_precision`: relevant / (relevant + irrelevant), excluding unknown evidence.
- `router_accuracy`: selected mode matches `expected_mode` for `auto` cases. Applicable only when the requested mode is `auto` and `expected_mode` is present.
- `answerability_accuracy`: production Evidence Support Gate answerability matches `expected_answerable`. The gate is deterministic and uses query-type mandatory checks such as requested attribute coverage, relation support, exact technical identifier coverage, and reason/definition signals.
- `evidence_support_score`, `evidence_support_reason`, `evidence_support_query_type`, and `evidence_support_signals`: debugging fields emitted by the production support evaluator.
- `retrieval_latency_ms`: elapsed retrieval call time. `total_eval_latency_ms`: elapsed per-case retrieval plus heuristic QA, measured before metric evaluation. Both exclude ingestion/index construction, HTTP, frontend rendering, and external LLM generation.
- `page_provenance_hit`: every expected physical page has citation-ready canonical evidence from an expected document, matching `page_number` and `source_locator=page:N` and at least one expected phrase when supplied. Non-applicable when no pages are expected.
- `expected_document_in_raw_candidates` / `expected_evidence_in_raw_candidates`: whether the retriever returned the expected document and phrase before context selection.
- `expected_document_in_final_context` / `expected_evidence_in_final_context`: whether expected material survived context selection.
- `expected_document_in_final_selection` / `expected_evidence_in_final_selection`: whether expected material reached canonical final evidence.
- `failure_stage`: the earliest diagnosable loss point. Values include `retrieval_document_miss`, `raw_candidate_miss`, `final_context_miss`, `evidence_selection_miss`, `support_gate_miss`, `expected_phrase_format_mismatch`, `genuine_no_answer`, and `success`.

The harness is deterministic and does not use LLM-as-judge. The support score is
not a semantic correctness score; it explains why the rule-based production gate
allowed or rejected the final evidence.

The canonical final evidence source is `RetrievalResult.evidences`. Retrieval metadata such as `initial_chunks`, `context_chunks`, and `evidence_units` is useful for debugging, but summary metrics do not treat raw chunks as final citation evidence. When the reranker is enabled, `RetrievalResult.evidences` contains the aligned final evidence.

Document Recall@K/MRR use the retriever's ordered `metadata.initial_chunks`, before context selection, QA evidence narrowing, and optional evidence reranking. Keep the first occurrence of each document; do not re-sort by score. IDs define relevance when `expected_doc_ids` is supplied; otherwise names use the existing case-insensitive identity convention. The compact `ranked_retrieved_documents` snapshot includes rank, ID/name, and the first chunk's existing score. That score explains the candidate; it is not a new document-level score. The ranking covers returned candidates (limited by mode/top_k), not an exhaustive collection search. Missing ranking metadata produces `null`; an explicitly empty ranking produces a miss. There is no fallback to generated citations.

For the new recalls and MRR, `expected_answerable=false` or `category=no_answer` excludes a case. Expected document identity is additionally required for document metrics. Failed applicable cases contribute zero; aggregate recalls and MRR are macro means over non-null case values, with `applicable` counts. Existing hit and evidence precision applicability rules are preserved.

Expected phrase checks normalize presentation-only differences: Markdown
backticks and emphasis, repeated whitespace, case, quotes, Unicode punctuation,
and terminal punctuation. They preserve numbers, underscores, hyphens, path
separators, API paths, and CLI flags. For example, formatted and unformatted
`CHUNK_STRATEGY` are equivalent, while `docker compose down` and
`docker compose down -v` are not.

Summary tables show `passed / applicable (percentage)`. `null` or non-applicable metrics are skipped from the denominator, so no-answer cases do not dilute ordinary retrieval/citation rates.

The legacy `failure_stage=success` describes survival of expected evidence and support-gate acceptance. It can coexist with forbidden evidence or low precision; failure reasons and evidence metrics must be inspected separately. No combined overall score is calculated.

## Multi-format Corpus

`tests/eval/format_corpus.json` is a small declarative fixture source; `tests/eval/rag_format_cases.jsonl` contains 24 cases. Each format has six cases: technical identifier, factual lookup, section-scoped recovery instruction, current-versus-archive distractor, structured memory-budget fact, and no-answer release date. There are 20 answerable and four no-answer cases, with one current and one archive document per format.

The existing runner generates TXT, Markdown, minimal valid DOCX packages, and native-text PDFs into a temporary directory, then processes and indexes them into its isolated eval KB. No extra parser/framework/dependency is introduced. ZIP timestamps and PDF IDs are fixed; manifests record fixture hashes, size, format, spec hash, and PyMuPDF version. Reproducibility is scoped to the same generator/library versions.

Facts and categories are closely related across formats, with distinct runtime names/identifiers. This is coverage through the shared RAG path, not a pure format ablation or a requirement for identical block boundaries. TXT/Markdown include a pipe table; DOCX/PDF use simple field/value prose. PDF audit and memory facts are on physical page 2 and have explicit page expectations. Complex layout, scanned PDFs, OCR, and native PDF table recognition are outside this slice.

`make eval-rag-format` defaults to `auto`, `block_aware`, `local_hashed_bow/hashed_bow_v1`, and disabled/noop reranking, like the deterministic generalization command. It writes `run.json`, `results.json`, and `summary.md` under `data/eval_runs/format-<timestamp>-<mode>-<strategy>/`. Each run regenerates and reindexes fixtures. Override `EVAL_MODE` or `EVAL_CHUNK_STRATEGY` for later controlled comparisons; no comparison/tuning is performed in M2.

Machine reports include stage metrics, format aggregates, failure-stage counts, and separate retrieval/total-eval latency summaries. Markdown shows overall/category/mode/format metrics, applicable denominators, no-answer cases, and failures. New unit tests cover ranking, multi-document recall, duplicate phrases/evidence, no-answer exclusions, old cases, serialization, and reporting; the format integration test exercises ingestion through canonical evidence and QA without score-based pass thresholds.

## Generalization Corpus

`tests/eval/corpus/` contains nine small Markdown-like `.txt` documents covering Python classes, FastAPI dependencies, PostgreSQL concurrency, Alice in Wonderland characters, synthetic team roles, synthetic device catalog data, employee policy no-answer cases, PureLink retrieval, and PureLink document processing.

The external-source documents are concise paraphrases for deterministic local evaluation. The runner does not fetch network resources at runtime. The corpus is intentionally small; it is designed to reveal retrieval and evidence-selection regressions, not to prove production quality.

Run output is written under `data/eval_runs/<run-id>/`:

- `run.json`: run id, commit, dirty worktree flag, corpus manifest, config, model identity, and duration.
- `results.json`: per-case selected mode, router reason, ranked document diagnostics, final evidence units, evidence metrics, answerability metrics, trace id, latency, and failure reasons; stage aggregates and optional format breakdowns.
- `summary.md`: run configuration, overall metrics, category/mode breakdowns, no-answer results, latency summary, failed cases, and known limitations.

The generated reports should be interpreted as phrase/doc based approximations. Latency is useful only for comparison on the same machine and configuration.

The committed 50-case generalization set is the deterministic regression suite. Its block-aware + hashed-BOW configuration answers whether a code change caused regression. The separate [fixed + FastEmbed snapshot](../../tests/eval/baselines/runtime-fastembed-fixed/summary.md) answers how the actual local Demo defaults perform. The two snapshots share cases and metric definitions but are not ranked as competing model benchmarks.

The independent holdout uses `tests/eval/holdout_corpus/` and
`tests/eval/rag_generalization_holdout_cases.jsonl`; it must remain separate
from the production-rule tuning loop. A fixture whose corpus does not contain
the requested fact should be modeled as no-answer and documented in case
notes, rather than counted as an answerable retrieval failure.

To write a sanitized local preview that can later become a committed baseline snapshot, use:

```bash
make eval-rag-generalization \
  GENERALIZATION_BASELINE_SNAPSHOT_DIR=tests/eval/baselines/answer-policy-auto-block-aware
```

The snapshot removes live trace ids, temporary database ids, absolute local paths, and secret-like configuration. It records commit SHA and dirty-worktree state. A dirty snapshot is acceptable evidence during review, but rerun it from the final clean commit before release/tagging.

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
7. Compare document Recall@1/@3/@5 and MRR, evidence recall/precision, citation and answerability, retaining legacy hits for historical comparisons.

Block-aware chunking should be evaluated empirically. It preserves document structure better, but it is not expected to improve every case.

## Comparing Retrieval Modes

The same JSONL case set can be run with different modes to compare recall behavior:

1. Run with `mode=chunk_only`.
2. Run with `mode=hybrid_text`.
3. Compare document Recall@K/MRR, evidence recall/precision, citation and answerability. Legacy hits remain available.

`hybrid_text` is expected to help exact technical queries. It should not be assumed to improve every semantic question.

## Adding a Generalization Case

1. Add or edit a small corpus document under `tests/eval/corpus/`.
2. Add one JSONL object to `tests/eval/rag_generalization_cases.jsonl`.
3. Include `expected_doc_names`, `expected_evidence_phrases`, and `forbidden_evidence_phrases` when the answer can be checked by phrases.
4. Use `expected_answerable=false` only when the answer is intentionally absent from the corpus.
5. Run `make eval-rag-generalization` and review failed cases instead of deleting them.
