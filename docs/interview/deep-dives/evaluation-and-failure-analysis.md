# Evaluation and Failure Analysis

## Purpose

This guide explains what the committed PureLink generalization baseline measures, how its denominators work, which failures remain visible, and how to present the results honestly in an interview.

## 30-second interview answer

PureLink has a deterministic 50-case regression baseline over a small cross-domain corpus, using block-aware ingestion, AUTO routing, local hashed embeddings, and no reranker. It reached 42/45 expected-document retrieval and citation hits, 32/45 expected-evidence hits, 50/50 router and evidence-gate answerability accuracy, and 50/50 trace availability. The result is useful for local regression, not a production benchmark: no LLM judge is used, evidence precision is phrase-based, and overview/evidence-selection failures remain in the report.

## Problem Being Solved

RAG changes can appear correct on one demo question while breaking another category. A useful local baseline must therefore:

- rebuild a known corpus instead of relying on mutable developer data;
- separate expected-document recall from expected-evidence selection;
- include answerable and intentionally unanswerable questions;
- verify router decisions independently from retrieval and support decisions;
- retain forbidden-evidence leaks and failed cases rather than hiding them;
- avoid using an LLM to grade another LLM.

## End-to-End Flow

[`run_rag_generalization_eval.py`](../../../scripts/eval/run_rag_generalization_eval.py) creates an in-memory SQLite database and temporary upload/chunk/vector directories. It ingests the committed corpus through the real processing/indexing path, runs each case through [`retrieve()`](../../../app/services/retrieval/retrieval_service.py), applies the production Evidence Support Gate, invokes QA with a deterministic heuristic generator for answer-policy metadata, and writes run/results/summary artifacts.

```text
committed corpus + 50 JSONL cases
  -> temporary KB
  -> real parse/chunk/index path
  -> RetrievalRequest(mode=auto, strategy=block_aware)
  -> final RetrievalResult.evidences
  -> deterministic metrics
  -> production Evidence Support Gate
  -> deterministic QA/policy metadata
  -> complete per-case failures and summary
  -> sanitized committed snapshot
```

Metrics deliberately use canonical final `RetrievalResult.evidences`, not raw `initial_chunks` or intermediate `context_chunks`.

## Core Data Structures

- [`RagEvalCase`](../../../scripts/eval/rag_eval.py): question, expected mode/document/phrases, forbidden phrases, category, and expected answerability.
- [`RagEvalCaseResult`](../../../scripts/eval/rag_eval.py): retrieval/citation/evidence/router/support/policy metrics, final evidence snapshots, latency, and failure reasons.
- [`rag_generalization_cases.jsonl`](../../../tests/eval/rag_generalization_cases.jsonl): 50 committed cases.
- [`tests/eval/corpus`](../../../tests/eval/corpus/): small cross-domain source files covering PureLink, Python, PostgreSQL, FastAPI, policies, people, products, and Alice characters.
- [Committed baseline run metadata](../../../tests/eval/baselines/answer-policy-auto-block-aware/run.json), [results](../../../tests/eval/baselines/answer-policy-auto-block-aware/results.json), and [summary](../../../tests/eval/baselines/answer-policy-auto-block-aware/summary.md).

## Baseline Results

Run `20260713-095624-auto-block_aware` records 50 cases: 45 answerable and 5 no-answer. Configuration was `block_aware`, requested mode `auto`, `local_hashed_bow` / `hashed_bow_v1`, and noop reranking disabled.

| Metric | Committed result |
|---|---:|
| Total cases | 50 |
| Answerable cases | 45 |
| No-answer cases | 5 |
| Retrieval hit | 42 / 45 (93.3%) |
| Citation hit | 42 / 45 (93.3%) |
| Expected evidence hit | 32 / 45 (71.1%) |
| Forbidden evidence clean | 7 / 9 (77.8%) |
| Router accuracy | 50 / 50 (100.0%) |
| Evidence-gate answerability accuracy | 50 / 50 (100.0%) |
| Trace available | 50 / 50 (100.0%) |

Mean evidence precision was 30.9% over 46 applicable cases. In-process retrieval latency was mean 7.7 ms, p50 8 ms, p95 10 ms, and max 21 ms in that local run.

### What each metric means

| Metric | What it measures | What it does not prove |
|---|---|---|
| `retrieval_hit` | At least one final evidence item comes from an expected document; no-answer cases without expected documents are excluded | That the selected passage contains the requested fact |
| `citation_hit` | Final evidence includes an expected-document item with both persisted citation-unit id and source locator | That a generated answer used the citation correctly or is semantically true |
| `expected_evidence_hit` | An expected-document final evidence item contains at least one expected phrase | Complete answer coverage or paraphrase equivalence beyond listed phrases |
| `forbidden_evidence_clean` | No listed forbidden phrase appears in final evidence for applicable cases | Absence of every possible irrelevant fact |
| `router_accuracy` | AUTO's `selected_mode` equals the case's expected mode | Retrieval, support, citation, or answer correctness |
| `answerability_accuracy` | Production support gate's predicted answerability equals the case label | Quality of generated prose or claim-level entailment |
| `trace_available` | A retrieval trace id was produced | That every internal event or full prompt was stored |
| `evidence_precision` | `relevant / (relevant + irrelevant)` using expected document/phrases and forbidden phrases; unknown units are excluded | A semantic precision estimate over arbitrary language |
| latency | In-process retrieval/eval timing in one local environment | End-to-end upload, embedding build, HTTP, provider, or frontend latency |

The 5/5 no-answer result means the deterministic support gate rejected all five labeled unsupported questions. It does not mean the system can reject every unsupported real-world question.

## Verified Code Entry Points

- Runner: [`run_rag_generalization_eval.py`](../../../scripts/eval/run_rag_generalization_eval.py).
- Metrics and case schema: [`rag_eval.py`](../../../scripts/eval/rag_eval.py).
- Summary/snapshot rendering: [`rag_generalization.py`](../../../scripts/eval/rag_generalization.py).
- Production decisions under evaluation: [`query_router.py`](../../../app/services/retrieval/query_router.py), [`evidence_support.py`](../../../app/services/evidence_support.py), [`answer_policy.py`](../../../app/services/answer_policy.py).
- Usage and metric notes: [`tests/eval/README.md`](../../../tests/eval/README.md) and [RAG Evaluation](../../rag/rag-evaluation.md).

## Failure and Fallback Behavior

The committed report lists every failed case and one or more deterministic reasons:

- `expected_document_not_retrieved`: final evidence never reached the expected source;
- `expected_evidence_not_selected`: the expected source may be present, but no final evidence contains a configured expected phrase;
- `forbidden_evidence_selected`: a listed irrelevant/incorrect phrase leaked into final evidence;
- `citation_missing`: no citation-ready expected-source evidence survived;
- `router_mode_mismatch`, `unexpected_no_answer`, `unexpected_answerable`, or `trace_missing` when those checks fail.

### Current failure patterns

**Retrieval miss.** `tech_text_file_types`, `overview_fastapi_dependencies`, and `overview_team_members` missed the expected document at final evidence. This is a final-evidence miss, not necessarily proof that the source was absent from every raw candidate.

**Correct source, wrong expected evidence.** Several cases retrieve the right document but select a nearby unit, including Python class definition/state/reason cases and technical supported-value/command/dependency cases. This explains why retrieval hit is 93.3% while expected-evidence hit is only 71.1%.

**Forbidden evidence leakage.** The baseline reports 7/9 clean applicable cases. `attr_alice_location` selects a conflicting Shanghai/partner fact, and `no_answer_processor` includes a forbidden color fact even though the support gate still correctly refuses the processor question.

**Overview weakness.** Overview is 3/5 on retrieval/citation hit and 2/5 on expected-evidence hit. Representative-chunk heuristics can over-select generic source-basis text from another document. It is the weakest category in this snapshot.

**Citation readiness vs semantic correctness.** A citation hit requires persisted unit provenance and the expected document, but the cited unit may still omit the expected phrase. Conversely, an evidence miss can coexist with a valid source locator. Readiness and semantic relevance are separate.

**Router accuracy vs answer quality.** AUTO selected the expected mode for all 50 cases, yet 13 answerable cases missed expected evidence and three missed expected documents. Routing is one stage, not whole-system accuracy.

## Tests and Verification

- [`tests/eval/test_rag_eval_metrics.py`](../../../tests/eval/test_rag_eval_metrics.py): nullable denominators, final-evidence metrics, support/policy metadata, latency, failure reasons, and sanitized snapshots.
- [`tests/eval/test_generalization_case_quality.py`](../../../tests/eval/test_generalization_case_quality.py): corpus/case quality and category constraints.
- [`tests/eval/test_rag_eval_baseline.py`](../../../tests/eval/test_rag_eval_baseline.py): baseline configuration and report generation.
- [`tests/services/retrieval/test_query_router_holdout.py`](../../../tests/services/retrieval/test_query_router_holdout.py): independent router phrasing outside the 50-case corpus.
- [`tests/services/test_evidence_support_holdout.py`](../../../tests/services/test_evidence_support_holdout.py): support-gate generalization checks.

The committed snapshot is immutable evidence for this report. A new run writes under `data/eval_runs/` unless an explicit snapshot directory is supplied; generated local ids and paths are sanitized before a snapshot is committed.

## Design Trade-offs

- Expected/forbidden phrases are reproducible and inspectable, but do not understand arbitrary paraphrases.
- A small corpus makes local runs fast enough for regression, but limits domain and language coverage.
- Running production retrieval/support code increases realism, while the deterministic heuristic answer generator deliberately avoids provider variability.
- Keeping failed cases in the summary makes regressions visible but means aggregate metrics require category-level interpretation.

## Known Limitations

- This is a deterministic local regression baseline, not a production benchmark or external leaderboard.
- There is no LLM-as-judge and no human relevance grading in the committed metric calculation.
- Evidence precision is an approximation and excludes unknown units from its denominator.
- Latency is meaningful only for comparisons on similar local hardware/configuration and excludes provider generation.
- The corpus contains 50 curated questions and a small set of text documents; it does not cover arbitrary uploads, OCR quality, or adversarial prompts.
- Expected evidence hit and forbidden evidence clean are not full scores, and overview retrieval remains comparatively weak.

## How to Present the Eval Honestly

Use this framing:

> "I built a 50-case deterministic cross-domain regression suite around the real ingestion and retrieval path. It validates routing, expected-document recall, citation readiness, phrase-level evidence selection, forbidden-evidence leakage, support-gate answerability, and trace availability. The committed run got 42/45 retrieval and citation hits and 32/45 expected-evidence hits. Router and answerability labels were 50/50, but that is not 100% QA accuracy; overview and evidence selection still have documented failures."

Then show one failure where the expected document was found but the expected unit was not. It demonstrates why retrieval hit, evidence hit, citation readiness, and answerability are separate metrics.

## Common Interview Follow-ups

**Why no LLM judge?** Deterministic phrases and labels make regressions reproducible and avoid judge-model cost and variance. The trade-off is weaker semantic coverage.

**Why is router accuracy 100% but evidence hit 71.1%?** The router only chooses a mode. Candidate recall and unit selection still determine whether the expected fact survives.

**Does citation hit mean the answer is correct?** No. It means expected-source final evidence has canonical unit and locator provenance.

**How are no-answer cases counted?** They are excluded from expected-document denominators when no expected document exists, but included in answerability accuracy.

**Why is evidence precision only 30.9%?** The phrase-based metric labels many unrecognized units as unknown and measures only recognized relevant versus irrelevant items. It exposes noise but is not semantic precision.

**What would you improve next?** Add larger blinded holdouts and human-reviewed relevance/claim support while keeping deterministic regression checks.

## Concise Answer Examples

**Result:** "The baseline proves repeatable local behavior, not universal correctness: 42/45 source and citation hits, 32/45 expected-evidence hits, and all failures listed."

**Router metric:** "50/50 means mode classification matched curated labels; it is not end-to-end answer accuracy."

**Failure analysis:** "The gap between document hit and evidence hit localizes most remaining work to unit selection rather than routing alone."
