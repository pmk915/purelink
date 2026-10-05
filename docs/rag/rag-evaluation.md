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

The subsequent [M3 evidence-selection ablation](evidence-selection-ablation.md)
records baseline, coverage-only, and combined results with fixed cases/corpus and
retrieval configuration. Generic factual selection now adds units only for new
meaningful query-term coverage when direct lexical support is strong; weak
signals retain the old per-chunk quotas. Existing entity profiles, technical
queries, and overview selection preserve their paths. A separate shared
responsibility alias/owner-binding correction resolves valid passive maintainer
support without relaxing mandatory checks or changing Answer Policy. Final
units retain their source text, IDs, locators and spans. The report includes
precision denominators, intermediate regressions, and remaining failures.

Default Runtime evaluation over the same 50 cases:

```bash
make eval-rag-runtime
```

Custom cases:

```bash
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

## Public Retrieval Validation

The external developer benchmark uses the official [MTEB package](https://github.com/embeddings-benchmark/mteb)
and its predefined `NanoBEIR` benchmark (13 tasks in MTEB 2.22.5). Start with
`NanoSciFactRetrieval` to validate installation, model/data loading, official scoring,
and serialization. Task membership comes from MTEB, rather than a selected list.

This is separate from the internal 50-case deterministic regression, 24-case
multi-format benchmark, and M2 → M3 evidence-selection ablation. Internal suites
diagnose PureLink-specific ingestion, routing, evidence, and provenance behavior;
NanoBEIR supplies a public retrieval reference. There is no QA generation, Answer
Policy, evidence selection, citation processing, PDF ingestion, or GraphRAG in
the external adapter. A local run does not give PureLink an official MTEB
leaderboard rank; no results are submitted automatically.

| Profile | Provider / model | Purpose |
|---|---|---|
| Internal regression | local_hashed_bow / hashed_bow_v1 | Deterministic system checks |
| Local Demo | fastembed / BAAI/bge-small-zh-v1.5 | Existing default, unchanged |
| Public English | fastembed / BAAI/bge-small-en-v1.5, normalize=true | English NanoBEIR corpus |

The public profile is scoped to the runner process. It never writes `.env` or
changes application defaults. MTEB stays out of production/Docker requirements.
For the CPU environment used here:

```bash
.venv/bin/python -m pip install 'torch==2.5.1+cpu' --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements-benchmark.txt
make eval-retrieval-nanobeir PUBLIC_EVAL_SMOKE=1 PUBLIC_EVAL_MODES=official
make eval-retrieval-nanobeir PUBLIC_EVAL_MODES='official dense'
make eval-retrieval-nanobeir
```

For a resource-limited validation, explicitly choose the first tasks in the
predefined MTEB order: `make eval-retrieval-nanobeir PUBLIC_EVAL_TASK_LIMIT=6`.
This is a partial NanoBEIR run. Remaining tasks are recorded as `not_run` with
the scope limit as the reason, and excluded from the shared-task macro. Task
selection never depends on scores. The M4 CPU run was limited to the first six
tasks at the user's request while task five was running; the default command
still attempts the full predefined benchmark.

Pass `PUBLIC_EVAL_BASELINE_SHA=<full-clean-baseline-SHA>` to record the initial
baseline separately from the run's current SHA and dirty flag. Optional command
variables are `PUBLIC_EVAL_OUTPUT_DIR` and `PYTHON`; the Python runner also accepts
`--cache-dir` and `--run-id`. External runs explicitly require network access for
official datasets/model downloads. All default results and caches live under
gitignored `data/eval_runs/external/`. CI uses synthetic in-memory data and never
downloads public datasets or model weights.

The first controlled run uses FastEmbed's quantized English ONNX model and
`CPUExecutionProvider`, including for the direct official baseline. CUDA hardware
alone does not make the CPU ONNX Runtime use a GPU. A GPU run would require a
compatible GPU ONNX Runtime/CUDA/cuDNN environment and explicit, verified model
execution providers; a CUDA PyTorch wheel alone does not accelerate FastEmbed.
Keep the backend fixed across compared configurations and record it separately.

Documents use nonempty official title + newline + official text, one benchmark
document per chunk. No synthetic headings or task instructions are added. The
direct embedding-only encoder reconstructs this representation from MTEB's
original `title`/`body` fields, so title concatenation is consistent. FastEmbed
owns model-specific query/document preprocessing. `query_embed()` and
`passage_embed()` replace PureLink's previous generic `query:`/`passage:` prefixes;
older implementations lacking those methods fall back narrowly to `embed()`
with raw text. Encoding failures are propagated, rather than retried with a
different preprocessing scheme. LocalHashedBow and other providers are unchanged.

Existing FastEmbed indexes must be rebuilt after this semantic correction to
avoid mixing previously prefixed document vectors with new query vectors. The
model identity alone does not detect that old preprocessing. Historical committed
snapshots remain historical; current runtime regressions go to fresh ignored run
directories. Do not use `make eval-rag-runtime` to preserve those snapshots during
this audit, because that existing target explicitly writes its snapshot directory.

Primary metric is nDCG@10; Recall@10, MRR@10, and Recall@5 are also reported using
official relevance judgments. Missing relevant documents remain in the recall
and ideal-DCG denominators. Reports preserve per-task results, corpus/query counts,
failures, versions, model/dimension, normalization, retrieval configuration,
duration, and macros over tasks completed by every compared configuration. There
is no combined score, phrase-based external metric, or LLM judge. Large unexplained
direct/dense discrepancies block the corresponding hybrid comparison. Hybrid
weights are kept at their production values; worse and mixed tasks remain visible.

The narrow adapter constructs the existing vector-artifact schema and an ephemeral
SQLite chunk table directly, without creating persisted users, teams, or product
knowledge bases. Dense calls production `search_index`; Hybrid calls production
`retrieve_hybrid_text_chunks`, including its inner lexical/metadata candidate
selection and outer keyword fusion with the existing keyword scorer and weights.
The same temporary vector index serves both PureLink modes.
Official MTEB uses float32 matrix cosine, while PureLink uses its Python cosine
scorer and normalizes query case/whitespace. Batch composition of quantized
encoding and tie ordering can also introduce small direct/dense differences.
The fixed discrepancy guard is 0.02 absolute for the reported metrics; it blocks
the task's Hybrid run when exceeded, rather than automatically changing settings.

Provider-only runtime comparison at the M4 baseline holds M3 code/cases and
FastEmbed 0.8.1 fixed, loading the old provider from `git show` in a separate
process. Recall@3 is 100% → 97.7%, MRR .9318 → .925, and Recall@1/5 remain
86.4%/100%. Retrieval and citation hits remain 44/44, evidence hits 36/44,
evidence recall 70.1%, precision 70.6% (41 cases), and answerability 47/50.
The changed rank expectations are `def_alice`, `def_aurora_pro`, and
`reason_low_score_refusal`; score/order details remain in ignored regression
artifacts. The deterministic 50-case and format-24 M3 results remain unchanged.

### M4 CPU result: first six NanoBEIR tasks

The initial run completed the first six tasks in MTEB's predefined order, with
50 queries per task (300 total) and 27,772 corpus records across tasks. The user
limited the scope while task five was running because of CPU cost; selection
was independent of scores. This is partial external validation, not a full
NanoBEIR result. All six official/Dense/Hybrid comparisons completed, and all
six direct/Dense discrepancy checks passed. There were no failed evaluated tasks.

Baseline and run HEAD: `c76e889ae414b5506c5a2a8dde3566b40920b872`; the initial
baseline was clean and the implementation run was dirty. Environment: Python
3.12.3, MTEB 2.22.5, FastEmbed 0.8.1, ONNX Runtime 1.30.0,
PyTorch 2.5.1+cpu, NumPy 2.2.6. Model: BAAI/bge-small-en-v1.5,
384 dimensions, normalized, quantized ONNX, CPU; top-k=10, reranker disabled/noop.
The cached model source is `Qdrant/bge-small-en-v1.5-onnx-Q`, revision
`aa8f8b060edb00e03bfdd08813a2949946c8ba55` (source revision was recorded from the
unchanged cache after the run). Evaluation wall time was 3,603 seconds, about
60 minutes. Model, representation, index, qrels, and production Hybrid weights
were held fixed for the PureLink comparison.

The separate official NanoSciFact smoke succeeded: nDCG@10=.7548,
Recall@10=.8200, MRR@10=.7392, Recall@5=.7950. It validates official MTEB
installation/scoring/serialization and is excluded from the six-task macro.

| Configuration | Macro nDCG@10 | Recall@10 | MRR@10 | Recall@5 |
|---|---:|---:|---:|---:|
| Official MTEB direct Dense | .6222 | .6710 | .6821 | .6034 |
| PureLink Dense | .6226 | .6710 | .6826 | .6034 |
| PureLink Hybrid | .5569 | .6340 | .6055 | .5516 |

All scores below are fractions; each task has 50 queries.

| Task | Corpus | Configuration | nDCG@10 | Recall@10 | MRR@10 |
|---|---:|---|---:|---:|---:|
| NanoArguAnaRetrieval | 3,635 | Official | .6362 | .9200 | .5436 |
| NanoArguAnaRetrieval | 3,635 | Dense | .6387 | .9200 | .5467 |
| NanoArguAnaRetrieval | 3,635 | Hybrid | .4926 | .9200 | .3595 |
| NanoClimateFeverRetrieval | 3,408 | Official | .3059 | .3913 | .4033 |
| NanoClimateFeverRetrieval | 3,408 | Dense | .3058 | .3913 | .4033 |
| NanoClimateFeverRetrieval | 3,408 | Hybrid | .3001 | .3390 | .4245 |
| NanoDBPediaRetrieval | 6,045 | Official | .5806 | .3202 | .7987 |
| NanoDBPediaRetrieval | 6,045 | Dense | .5806 | .3202 | .7987 |
| NanoDBPediaRetrieval | 6,045 | Hybrid | .5254 | .3187 | .7014 |
| NanoFEVERRetrieval | 4,996 | Official | .9207 | .9633 | .9319 |
| NanoFEVERRetrieval | 4,996 | Dense | .9207 | .9633 | .9319 |
| NanoFEVERRetrieval | 4,996 | Hybrid | .8698 | .9233 | .8756 |
| NanoFiQA2018Retrieval | 4,598 | Official | .4718 | .5711 | .5277 |
| NanoFiQA2018Retrieval | 4,598 | Dense | .4718 | .5711 | .5277 |
| NanoFiQA2018Retrieval | 4,598 | Hybrid | .3410 | .4431 | .3600 |
| NanoHotpotQARetrieval | 5,090 | Official | .8178 | .8600 | .8872 |
| NanoHotpotQARetrieval | 5,090 | Dense | .8178 | .8600 | .8872 |
| NanoHotpotQARetrieval | 5,090 | Hybrid | .8126 | .8600 | .9117 |

The remaining NanoMSMARCORetrieval, NanoNFCorpusRetrieval, NanoNQRetrieval,
NanoQuoraRetrieval, NanoSCIDOCSRetrieval, NanoSciFactRetrieval, and
NanoTouche2020Retrieval are explicitly `not_run` in all compared modes because
of the user's scope limit. The already-running original loop was intentionally
interrupted after the sixth task was saved, during task seven's initial data
discovery; no seventh-task embedding/evaluation completed. This scope stop is
recorded separately from task failures. Future partial runs use the task-limit
parameter and finish normally. The optional reranker comparison was omitted;
no new reranker model/dependency was introduced.

PureLink Dense closely matches the independent official reference (largest
task nDCG difference .00245). Hybrid lowers nDCG on all six tasks and its macro
by .0656; Recall@10 drops .0370 and MRR@10 drops .0771. ClimateFever and HotpotQA
MRR improve slightly, but their nDCG decreases. Keep the measured result and
stop tuning. These six tasks do not establish the result for all NanoBEIR tasks
or for the internal document/evidence benchmarks.

Read-only diagnosis of ArguAna rankings found 26 queries with lower Hybrid nDCG,
one with higher nDCG, and 23 unchanged. Some relevant rank-1 documents move to
rank 3–4 while Recall@10 remains unchanged. A likely contributor is the existing
substring term-coverage scorer without corpus-frequency weighting, together
with title/technical bonuses and the two candidate/fusion stages. The outer
merge normalizes candidates having both scores, while candidates having only
one score retain its raw scale. These are hypotheses from code and saved
rankings, not an isolated causal ablation; no scorer, weight, or cutoff changed.

Keep the FastEmbed API correctness fix, with a full rebuild of existing
FastEmbed indexes. The partial external results and their limitations are ready
to describe in README as local validation; no official leaderboard submission
or general Hybrid-improvement claim is warranted.

Reproduce this scope with `make eval-retrieval-nanobeir PUBLIC_EVAL_TASK_LIMIT=6`.
Generated artifacts remain ignored under
`data/eval_runs/external/m4-nanobeir-initial/`: `run.json`, `summary.md`, official
results/predictions, and Dense/Hybrid rankings. The original pre-finalization
report and scope-stop event preserve how the running full attempt became a
six-task report. Regression artifacts remain under the separate
`data/eval_runs/external/m4-regression/` directory.

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
