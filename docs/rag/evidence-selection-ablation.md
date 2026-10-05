# M3 Evidence Selection Ablation

## Recorded baseline and diagnosis (before implementation)

Clean `main` at `8ec4dbe1814b6c95ed0e6273783c8710ed616bf9`.
Baseline artifacts: `data/eval_runs/m3-baseline/format-20261005-151956-auto-block_aware/`
and `data/eval_runs/m3-baseline/20261005-152014-auto-block_aware/`.
The former reproduces M2: Recall@1/3/5 85/100/100%, MRR .925,
expected evidence hit 18/20, evidence recall 90%, precision 29.6429%,
citation 20/20, answerability 20/24, forbidden cases 10, no-answer 4/4,
PDF page provenance 2/2. Answerable evidence count mean 6.6, median 8.
Stages: success 16, support_gate_miss 2, evidence_selection_miss 2,
genuine_no_answer 4. The 50-case baseline remains retrieval/citation 43/44,
evidence hit 39/44, answerability 49/50.

Read-only instrumentation saved `data/eval_runs/m3-baseline/diagnosis.json`:
question, ordered initial/context chunks, all scored citation-unit candidates,
selected units, final canonical evidence, support/policy decisions. Each case
below was inspected through these stages. A = wrong document; C = unnecessary
sibling; D = broad lexical overlap; E = over-selection; G = attribute binding;
H = support interaction. No exact duplicate units materially explain this run.

| Case | Expected support | Selected forbidden support | Noise entry / cause |
|---|---|---|---|
| txt_factual_lookup | current maintainer | Rowan Lee | Archive enters initial/context; generic selector retains it (A/D/E). Correct maintainer survives; gate rejects passive wording/entity binding (G/H). |
| markdown_factual_lookup | current maintainer | Rowan Lee | Same A/D/E and G/H path. |
| txt_distractor_sensitive | 14 days | 90 days | Archive enters initial/context; matching audit terms survive final selection (A/D/E). |
| markdown_distractor_sensitive | 14 days | 90 days | Same A/D/E path. |
| docx_distractor_sensitive | 14 days | 90 days | Same A/D/E path, plus broad sibling units. |
| pdf_distractor_sensitive | 14 days, page 2 | 90 days | Same A/D/E path; page provenance is already correct. |
| txt_structured_fact | compact 384 MiB | standard 768 MiB | Both rows occupy one citation unit; final unit also brings unrelated documents (C/A/E). |
| markdown_structured_fact | compact 384 MiB | standard 768 MiB | Same inseparable table-unit C plus A/E. |
| docx_structured_fact | compact 384 MiB | standard 768 MiB | Same-document sibling field retained despite already covering compact fact (C/D/E). |
| pdf_structured_fact | compact 384 MiB, page 2 | standard 768 MiB | Neighbor format documents survive; their standard fields contaminate final evidence (A/C/E). |
| docx_factual_lookup | current maintainer | none labeled | Correct unit exists in initial/context and scored candidates, but per-chunk two-unit limit favors runtime/default lines. Then responsibility gate rejects (E/G/H). |
| pdf_factual_lookup | current maintainer | none labeled | Same competition; no heading metadata benefit for passive statement. Then gate rejects (E/G/H). |

The four maintainer failures have both selection pressure and a distinct matcher
defect. TXT/Markdown already present the correct statement, so tightening count
alone cannot fix their support rejection. Table rows inside a single citation
unit are a granularity limit; this milestone will not split or reparse them.

## Hypotheses and boundaries

Primary: select generic factual evidence by incremental coverage of meaningful
query terms in **unit text**, not inherited headings. Consider all eligible
units in existing context chunks before a per-chunk quota can discard a useful
fact. Prefer largest coverage gain, break ties by existing score/order, and stop
when no new query term is covered. Preserve the existing maximum and original
citation identities/spans. Existing entity, technical and overview selectors
remain in place. Do not add a model, reranker, forbidden-label filter, or a fixed
one-unit cap. Independent facets can require multiple units.

Trade-off: lexical compression can lose paraphrased support or distinct facts
that use the same query words. Label-only fragments should not displace a fact;
unsupported/zero-signal cases must retain the existing conservative behavior.
Compare precision and recall together, not evidence count alone.

Implemented guard: compress only when the best eligible unit covers at least
half the meaningful query terms. Otherwise restore the old two-unit-per-chunk
quota and global score order. Respect both query analysis and the existing
entity profile; a legacy entity profile must not enter the generic branch.
This keeps existing paraphrased/multi-source answers and entity isolation.
For strong generic coverage, the existing score remains a tie-breaker; no
retrieval weight or candidate score is changed. Redundant query coverage stops
selection without adding a separate overlap subsystem.

Second, independent correctness fix: share active/passive responsibility aliases
between selector and support, and bind English maintainer questions to the named
target rather than Who/function words. Keep mandatory support checks, entity
isolation, Answer Policy, and prompts unchanged. Evaluate coverage-only as well
as the combined change so this fix is not hidden inside a score gain.

Hold corpus/cases, embedding, chunk strategy, retrieval mode/top-k, reranker,
Answer Policy and environment constant. No holdout tuning or architecture work.

## Controlled results

All runs used auto, block-aware, local_hashed_bow/hashed_bow_v1, disabled/noop
reranking, retrieval minimum score .15, Python 3.12.3 and PyMuPDF 1.27.2.3.
Top-k remains the existing case value (8). Checks confirmed identical fixture
manifests/hashes, case ids/questions, ranked document snapshots including scores,
and selected router modes. Answer Policy code, prompts and support thresholds
are unchanged. The shared responsibility matcher/binding fix is explicitly a
second intervention; the primary-only column isolates it.

| Format metric | M2 selector | Coverage only | M3 combined |
|---|---:|---:|---:|
| Recall@1 (n=20) | 85% | 85% | 85% |
| Recall@3 (n=20) | 100% | 100% | 100% |
| Recall@5 (n=20) | 100% | 100% | 100% |
| MRR (n=20) | .925 | .925 | .925 |
| Expected evidence hit | 18/20 | 16/20 | 20/20 |
| Evidence recall (n=20) | 90% | 80% | 100% |
| Evidence precision | 29.6429% (n=20) | 78.125% (n=16) | 72.5% (n=20) |
| Forbidden evidence cases | 10 | 3 | 7 |
| Mean / median units per answerable case | 6.6 / 8 | 1.25 / 1 | 1.45 / 1 |
| Retrieval hit | 20/20 | 20/20 | 20/20 |
| Citation hit | 20/20 | 20/20 | 20/20 |
| Answerability | 20/24 | 20/24 | 24/24 |
| No-answer correctness | 4/4 | 4/4 | 4/4 |
| PDF page provenance | 2/2 | 2/2 | 2/2 |

Precision applicability must not be hidden: coverage-only turns four maintainer
cases into unknown-only evidence, excluded by the unchanged precision formula.
Its higher precision therefore accompanies worse recall and is not the retained
configuration. The combined fix recovers all expected phrases and supports all
four maintainer questions, but also retains archive maintainer statements.
No additional exclusion rules or semantic contradiction detector were added.

Format stages: baseline success 16 / support_gate_miss 2 /
evidence_selection_miss 2 / genuine_no_answer 4; primary-only success 16 /
evidence_selection_miss 4 / genuine_no_answer 4; combined success 20 /
genuine_no_answer 4. Legacy success still does not assert clean evidence.

| Format (6 cases; 5 answerable) | Precision before / after | Recall before / after | Evidence hit before / after | Answerability before / after |
|---|---:|---:|---:|---:|
| TXT | 30% / 60% | 100% / 100% | 5/5 / 5/5 | 5/6 / 6/6 |
| Markdown | 30% / 70% | 100% / 100% | 5/5 / 5/5 | 5/6 / 6/6 |
| DOCX | 30% / 90% | 80% / 100% | 4/5 / 5/5 | 5/6 / 6/6 |
| PDF | 28.5714% / 70% | 80% / 100% | 4/5 / 5/5 | 5/6 / 6/6 |

All formats retain Recall@5=100%, citation hit 5/5, and their original MRR
(TXT/Markdown/DOCX .900; PDF 1.000). PDF page-2 expectations remain 2/2.

| Official 50-case metric | Before | M3 |
|---|---:|---:|
| Recall@1 / @3 / @5 (n=44) | 79.5455 / 93.1818 / 97.7273% | unchanged |
| MRR (n=44) | .867424 | unchanged |
| Retrieval / citation hit | 43/44 | 43/44 |
| Expected evidence hit | 39/44 | 39/44 |
| Evidence recall (n=44) | 79.1667% | 79.1667% |
| Evidence precision (n=42) | 72.3271% | 72.3271% |
| Answerability | 49/50 | 49/50 |
| No-answer correctness | 6/6 | 6/6 |
| Forbidden answerable cases | 0 | 0 |
| Mean / median answerable evidence count | 3.4091 / 2 | 3.4091 / 2 |

Official metrics/failure stages/evidence counts match per case, not just in
aggregate. Stages remain success 36, genuine_no_answer 6, raw_candidate_miss 3,
expected_phrase_format_mismatch 3, final_context_miss 1, retrieval_document_miss 1.
There is no retained regression in either suite's evidence recall.

Initial development without the lexical-confidence and entity-profile guards
over-compressed paraphrases, broke four existing tests, and reduced official
retrieval/citation to 42/44 and evidence hit to 38/44. That variant was rejected.
The final guards restore the existing weak-signal quotas and entity selection.
The PDF provenance test now explicitly requests both first/second-page facts;
it still verifies both strategies, both pages, source spans, and final evidence.
Benchmark cases/labels were not changed. This records the observable limitation:
two independent facts using identical query terms can be compressed when the
question does not expose separate facets.

## Remaining failures and decision

Seven combined format cases still select forbidden evidence:

- `txt_factual_lookup`, `markdown_factual_lookup`, `docx_factual_lookup`,
  `pdf_factual_lookup`: correct and archived maintainer statements coexist.
- `txt_structured_fact`, `markdown_structured_fact`: compact and standard values
  are inseparable inside one citation unit. Units were not clipped or reparsed.
- `pdf_structured_fact`: another document's table adds the query word reserved,
  bringing its standard value along. Lexical novelty does not prove relevance.

Five official evidence failures remain unchanged: `attr_instance_state`
(final context), `reason_python_classes`, `reason_reprocess_old_docs`,
`reason_low_score_refusal` (raw candidates), and `tech_text_file_types`
(document miss / unsupported answer). Three normalization-only stage labels
also remain. These are recorded, not removed or optimized here.

Keep the combined change: precision improves by 42.8571 percentage points,
expected phrase recall improves by 10 points, and document ranking, citation
grounding, no-answer correctness and official regression remain intact.
These small deterministic suites do not establish production-scale quality or
semantic correctness. Capitalization-based owner binding and lexical novelty
remain conservative heuristics, with same-facet, temporal, and table limits.
Stop substantive optimization here; next work is final benchmark capture,
README/results synchronization and demo/interview packaging.

## Artifacts and reproduction

Final local artifacts are ignored and historical committed baselines are intact:

- Primary only: `data/eval_runs/m3-primary-final/format-20261005-153402-auto-block_aware/`.
- Combined format: `data/eval_runs/m3-capture/format-20261005-153423-auto-block_aware/`.
- Combined official: `data/eval_runs/m3-capture/20261005-153423-auto-block_aware/`.
- Machine comparison: `data/eval_runs/m3-comparison.json`.
- Every run directory includes run.json, results.json and summary.md; the
  baseline diagnosis JSON contains all inspected stage/candidate text.

Capture M2 from a clean checkout of the baseline SHA using the same two Make
commands. Capture M3 from this workspace with:

```bash
make eval-rag-format FORMAT_EVAL_OUTPUT_DIR=data/eval_runs/m3-capture
make eval-rag-generalization GENERALIZATION_EVAL_OUTPUT_DIR=data/eval_runs/m3-capture
```

For primary-only isolation, the existing runner was invoked in a temporary
Python process with the baseline responsibility alias tuple and baseline
`_extract_evidence_entities` function temporarily restored via unittest.mock.
The source was read with `git show 8ec4dbe:app/services/query_analysis.py`;
no production toggle, framework, code rollback or alternate retrieval path was
introduced. Both selector and support use the same temporarily restored matcher.

Local format retrieval latency mean/p95: 6.0833/7 ms baseline, 5.875/8 ms M3;
total eval 8.25/13 ms baseline, 8.0417/13 ms M3. Official retrieval mean/p95:
8.84/11 ms baseline, 9.06/13 ms M3; total eval 10.68/15 ms baseline, 10.96/15 ms
M3. Final runs overlapped backend validation; no performance improvement is
claimed. Timing excludes ingestion/indexing and external LLM generation.

## Verification

Added 12 deterministic tests for direct text versus headings/siblings,
cross-document noise, duplicate support, multiple independent facets, lexical
confidence fallback, exact technical identifiers, missing attributes/no-answer,
owner binding, passive wording, entity isolation and source provenance.
The existing PDF test keeps two-page assertions with an explicit two-page query.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/services/test_evidence_selection_coverage.py tests/test_citation_units.py \
  tests/test_retrieval_pipeline.py tests/services/test_query_analysis.py \
  tests/services/test_evidence_support.py tests/services/test_answer_policy.py tests/eval
# 276 passed in 2.66s
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests
# 709 passed, 22 skipped in 36.73s
make docs-check
# 60 Markdown files, no broken relative links
git diff --check
# clean
```

Only qa.py and query_analysis.py change production behavior. No migrations,
models, retrieval/router/embedding/reranker configuration, PDF parsing, chunk
strategy, benchmark corpus/labels, historical snapshots, Answer Policy or
prompts were changed. The independent holdout benchmark was not used for
tuning. Git status/diff were reviewed; all M3 changes remain uncommitted.
