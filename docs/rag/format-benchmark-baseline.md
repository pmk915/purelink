# M2 Deterministic Format Benchmark Baseline

This is a small deterministic engineering benchmark, measured before retrieval
optimization. It supplements the official 50-case regression and independent
holdout. Production ranking, weights, embedding, reranking, QA policies, and
prompts were not changed in M2. Existing uncommitted M1 PDF changes were included
in the measured workspace.

Reproduce with:

```bash
make eval-rag-generalization
make eval-rag-format
```

Measured on 2026-10-05, branch `main`, HEAD
`3b098d971b8840c7e5149e0f553fa13201d0cea6`, dirty worktree. Both commands used
`auto`, `block_aware`, `local_hashed_bow/hashed_bow_v1`, disabled/noop reranking,
and retrieval minimum score 0.15. Python: 3.12.3; PyMuPDF: 1.27.2.3.

Local artifacts (ignored; historical committed snapshots were not overwritten):

- Format: `data/eval_runs/format-20261005-145124-auto-block_aware/`.
- Generalization: `data/eval_runs/20261005-145124-auto-block_aware/`.
- Each directory contains `run.json`, `results.json`, and `summary.md`.

The format run records the declarative corpus spec hash, generated fixture
hashes, and library version. Regenerate fixtures with the same generator/library
versions for reproducibility. This dirty-worktree run describes the reviewed
implementation; it is not a clean release snapshot.

There are eight documents: a current manual and an archive per format. The
24 cases comprise six each for TXT, Markdown, DOCX, and PDF; each format has five
answerable and one no-answer case. Categories are technical identifier, factual
lookup, section-scoped instruction, distractor-sensitive fact, structured fact,
and no-answer (four cases per category). PDF has two page-2 citation expectations.
The corpus uses closely related facts with distinct names/identifiers, so these
are format-coverage measurements, not a pure causal format ablation.

| Metric | Format slice | Official regression rerun |
|---|---:|---:|
| Cases | 24 | 50 |
| Document Recall@1 | 85.0% (n=20) | 79.5% (n=44) |
| Document Recall@3 | 100.0% (n=20) | 93.2% (n=44) |
| Document Recall@5 | 100.0% (n=20) | 97.7% (n=44) |
| Document MRR | 0.925 (n=20) | 0.867424 (n=44) |
| Legacy retrieval hit | 20/20 | 43/44 |
| Expected evidence hit | 18/20 | 39/44 |
| Evidence recall | 90.0% (n=20) | 79.1667% (n=44) |
| Evidence precision | 29.6429% (n=20) | 72.3271% (n=42) |
| Citation hit | 20/20 | 43/44 |
| Answerability accuracy | 20/24 | 49/50 |
| Forbidden evidence clean | 6/16 | 9/9 |
| No-answer correctness | 4/4 | 6/6 |
| Page provenance hit | 2/2 | n/a |
| Trace available | 24/24 | 50/50 |

Per-format recall, MRR, and precision means have n=5 (answerable cases).
Answerability includes the sixth, no-answer case.

| Format | Cases | Recall@5 | MRR | Evidence hit | Evidence recall | Evidence precision | Citation hit | Answerability | Page provenance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TXT | 6 | 100% | 0.900 | 5/5 | 100% | 30.0% | 5/5 | 5/6 | n/a |
| Markdown | 6 | 100% | 0.900 | 5/5 | 100% | 30.0% | 5/5 | 5/6 | n/a |
| DOCX | 6 | 100% | 0.900 | 4/5 | 80% | 30.0% | 5/5 | 5/6 | n/a |
| PDF | 6 | 100% | 1.000 | 4/5 | 80% | 28.5714% | 5/5 | 5/6 | 2/2 |

Format failure stages: `success` 16, `support_gate_miss` 2,
`evidence_selection_miss` 2, `genuine_no_answer` 4. All four factual maintainer
questions are rejected (`missing_attribute_support`). The expected phrase is
present in raw candidates and final context in all four; TXT/Markdown retain it
in canonical final evidence, while DOCX/PDF lose it during selection. Ten cases
select forbidden evidence, including eight classified as legacy `success`.
That stage measures expected-evidence survival and support acceptance; it does
not assert clean evidence or high precision.

Official regression stages: `success` 36, `genuine_no_answer` 6,
`raw_candidate_miss` 3, `expected_phrase_format_mismatch` 3,
`final_context_miss` 1, `retrieval_document_miss` 1. Per-case legacy retrieval,
citation, evidence hit/precision, forbidden hit, router, answerability, top-1/3
hit, and failure-stage values match the committed answer-policy baseline.

| Suite / timing stage | Mean ms | p50 ms | p95 ms | Max ms | n |
|---|---:|---:|---:|---:|---:|
| Format / retrieval | 5.8 | 5 | 8 | 13 | 24 |
| Format / total eval | 8.2 | 7 | 14 | 17 | 24 |
| Generalization / retrieval | 8.92 | 9 | 13 | 24 | 50 |
| Generalization / total eval | 10.76 | 10 | 15 | 26 | 50 |

Timing is local in-process measurement; these runs overlapped backend
verification. It is not a performance claim. Total eval includes retrieval and
heuristic QA and is measured before metric evaluation; both timings exclude
ingestion/index construction and external LLM generation.

Metric definitions are in [RAG Evaluation](rag-evaluation.md). Recall@K and MRR
rank distinct documents by first occurrence in returned `initial_chunks`; they
prefer expected IDs, otherwise case-insensitive names. Final evidence metrics
use `RetrievalResult.evidences`. Evidence recall counts each distinct normalized
expected phrase once. Evidence precision retains the existing relevant /
(relevant + irrelevant) rule, excluding unknown units. New recall/MRR means
exclude no-answer cases; old metric semantics remain unchanged.

M3 hypotheses to test, without implementing them here:

1. Broad final evidence and archive/neighbor units may explain the low precision
   despite high document recall; controlled evidence-selection ablations could
   measure whether precision improves without losing recall or grounding.
2. Maintainer questions may be mismatched between attribute extraction, evidence
   narrowing, and support checks; diagnose each transition before changing rules.

Validation: focused eval tests **80 passed**; full backend tests **697 passed,
22 skipped**. Both benchmark commands completed and preserved existing failures.
No holdout tuning, commit, or push was performed.
