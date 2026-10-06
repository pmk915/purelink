# RAG Evaluation Talking Points

Keep three experiments separate. [RAG Evaluation](../rag/rag-evaluation.md) owns
metric definitions and reproduction; [Evidence Ablation](../rag/evidence-selection-ablation.md)
owns the controlled results. The historical 20-case repository-doc suite is not
the current interview regression story.

## A. Internal 50-case Regression

44 answerable / six no-answer cases; AUTO, block-aware, local_hashed_bow /
hashed_bow_v1, reranking disabled/noop. Retrieval/citation 43/44, expected evidence
39/44, answerability 49/50, no-answer 6/6. The historical sanitized snapshot is
[answer-policy-auto-block-aware](../../tests/eval/baselines/answer-policy-auto-block-aware/summary.md).
Final closeout measurements are recorded in [Portfolio Verification](../development/portfolio-verification.md).
This deterministic engineering suite detects regression, not public or
production QA quality.

The normal Demo uses fixed chunking / Chinese FastEmbed. Its committed
[runtime snapshot](../../tests/eval/baselines/runtime-fastembed-fixed/summary.md)
is historical after the M4 provider correction. Provider-only checks keep
retrieval/citation 44/44, expected evidence 36/44, answerability 47/50;
Recall@3 changes 100% → 97.7% and MRR .9318 → .925. Keep the fix and fully rebuild
old FastEmbed indexes. Do not silently overwrite that snapshot.

## B. Controlled Evidence-selection Ablation

24 format cases: six per format, 20 answerable / four no-answer. Candidate ranking,
embedding, chunk strategy, corpus/cases, and Answer Policy stay fixed.

| Metric | M2 | Coverage-only (rejected) | M3 retained |
|---|---:|---:|---:|
| Recall@5 | 100% | 100% | 100% |
| MRR | .925 | .925 | .925 |
| Expected evidence hit | 18/20 | 16/20 | 20/20 |
| Evidence recall | 90% | 80% | 100% |
| Evidence precision | 29.6% (n=20) | 78.1% (n=16) | 72.5% (n=20) |
| Answerability | 20/24 | 20/24 | 24/24 |
| No-answer correctness | 4/4 | 4/4 | 4/4 |

The bottleneck was noisy selected evidence despite strong document recall.
Generic incremental term coverage plus a separately diagnosed shared
responsibility-matching fix improved the retained configuration. Selection alone
lost recall and was rejected. Seven format cases still select forbidden evidence;
archive/table/cross-document limits remain. Precision excludes unknown evidence,
so the coverage-only applicability change is part of the interpretation.

## C. Six-task Partial NanoBEIR External Validation

300 queries across the first six predefined tasks; remaining seven explicitly
unrun at the user runtime limit. BAAI/bge-small-en-v1.5, FastEmbed quantized ONNX,
384 normalized dimensions, CPU, top-k=10, reranking disabled, official title/text
and qrels held fixed.

| Pipeline | nDCG@10 | Recall@10 | MRR@10 |
|---|---:|---:|---:|
| MTEB Dense reference | .6222 | .6710 | .6821 |
| PureLink Dense | .6226 | .6710 | .6826 |
| PureLink Hybrid | .5569 | .6340 | .6055 |

All Dense reference checks passed. Hybrid nDCG fell on all six tasks; this
negative result was retained without public-task tuning. The separate NanoSciFact
smoke is excluded from the macro. No full NanoBEIR, official leaderboard rank,
or universal Hybrid superiority follows from this experiment.

## Metric Boundaries

Document Recall@K/MRR measure candidate ranking; final-evidence phrase recall
and precision measure selected support proxies; answerability measures the
production gate against labels. Retrieval hit does not imply clean evidence,
router accuracy does not imply answer accuracy, and a valid source marker does
not prove semantic correctness. No LLM judge or combined score is used.

## Reproduce Without Replacing History

```bash
make eval-rag-generalization GENERALIZATION_EVAL_OUTPUT_DIR=data/eval_runs/interview-check
make eval-rag-format FORMAT_EVAL_OUTPUT_DIR=data/eval_runs/interview-check
# Explicit external developer action; downloads optional dependencies/models/data:
make eval-retrieval-nanobeir PUBLIC_EVAL_TASK_LIMIT=6
```

Do not rerun the public benchmark for README-only changes. Do not use
`make eval-rag-runtime` casually: it explicitly writes the historical snapshot.
For fresh runtime measurements, invoke the runner without --baseline-snapshot-dir.

## Thirty-second Interview Answer

“I separated document retrieval from evidence selection, answer support, and
citations. High document recall exposed noisy evidence rather than a missing-doc
problem. Controlled ablation improved evidence precision and recall while a
lossy precision-only variant was rejected. An independent public reference
validated the Dense plumbing and showed the current Hybrid fusion was worse on
all six tasks. Those boundaries and negative results are part of the project.”
