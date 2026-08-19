# RAG Evaluation Talking Points

## One Official Regression Suite

The only current official interview regression suite is [`rag_generalization_cases.jsonl`](../../tests/eval/rag_generalization_cases.jsonl): 50 deterministic cases over nine small cross-domain documents, with 44 answerable and 6 no-answer cases. It exercises the real ingestion, indexing, routed retrieval, evidence selection, Evidence Support, Answer Policy, citation-readiness, and trace paths.

The earlier 20-case repository-doc comparison is historical. Its files remain for provenance, but its metrics and `make eval-rag-legacy-20` command are not the current interview result.

## Why Two Snapshots Exist

### Deterministic Regression Baseline

Configuration:

```env
CHUNK_STRATEGY=block_aware
EMBEDDING_PROVIDER=local_hashed_bow
EMBEDDING_MODEL=hashed_bow_v1
RERANKER_ENABLED=false
RERANKER_PROVIDER=noop
```

Question answered: “Did a system change cause regression?”

| Metric | Result |
|---|---:|
| retrieval_hit | 43 / 44 |
| citation_hit | 43 / 44 |
| expected_evidence_hit | 39 / 44 |
| forbidden_evidence_clean | 9 / 9 |
| mean_evidence_precision | 72.3% (n=42) |
| router_accuracy | 50 / 50 |
| answerability_accuracy | 49 / 50 |
| trace_available | 50 / 50 |

Snapshot: [answer-policy-auto-block-aware](../../tests/eval/baselines/answer-policy-auto-block-aware/summary.md).

### Default Runtime Evaluation

Configuration:

```env
CHUNK_STRATEGY=fixed
EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RERANKER_ENABLED=false
RERANKER_PROVIDER=noop
```

Question answered: “How does the actual Demo default perform?”

| Metric | Result |
|---|---:|
| retrieval_hit | 44 / 44 |
| citation_hit | 44 / 44 |
| expected_evidence_hit | 36 / 44 |
| forbidden_evidence_clean | 8 / 9 |
| mean_evidence_precision | 70.6% (n=41) |
| router_accuracy | 50 / 50 |
| answerability_accuracy | 47 / 50 |
| trace_available | 50 / 50 |

Snapshot: [runtime-fastembed-fixed](../../tests/eval/baselines/runtime-fastembed-fixed/summary.md).

Do not rank these as “simple versus advanced.” Hashed BoW is the repeatable regression fixture; FastEmbed describes the user-facing runtime. Both expose real failures.

## What the Metrics Mean

- `retrieval_hit`: final evidence contains an expected document.
- `citation_hit`: final evidence from the expected document is citation-ready.
- `expected_evidence_hit`: canonical final evidence contains an expected phrase.
- `forbidden_evidence_clean`: no explicitly forbidden phrase reached final evidence.
- `evidence_precision`: recognized relevant evidence divided by recognized relevant plus irrelevant evidence; unknown evidence is excluded.
- `router_accuracy`: AUTO selected the labeled expected mode.
- `answerability_accuracy`: the deterministic production support decision matched the case label.
- `trace_available`: a retrieval trace was persisted.

These are phrase/document heuristics, not semantic correctness or LLM-as-judge. Router accuracy is not answer quality, retrieval hit is not answerability, and 49/50 answerability does not imply 98% real-world QA accuracy.

## Evidence Selection Result

The final support-aware narrowing experiment applies only to explicit `entity_attribute`, `exact_technical`, and `entity_relation` support IDs. It preserves overview/generic breadth and keeps unsupported evidence available for diagnostics while Answer Policy skips the provider.

Against the pre-change working tree, deterministic precision improved from 67.3% to 72.3% while retrieval/citation stayed 43/44, expected evidence stayed 39/44, forbidden clean stayed 9/9, router stayed 50/50, and answerability stayed 49/50. The independent 20-case holdout was unchanged: retrieval/citation 16/16, expected evidence 13/16, forbidden clean 12/12, router/answerability/trace 20/20, and precision 100% on 13 applicable cases.

## Reproduce

```bash
make eval-rag-generalization
make eval-rag-generalization-holdout
make eval-rag-runtime
```

`make eval-rag-runtime` requires FastEmbed and the model cache; first use may download the model. Generated local runs go under `data/eval_runs/`; committed snapshots are sanitized.

## Interview Answer

> I use one 50-case cross-domain suite for the current interview regression story. The deterministic stack catches code regressions, while a separate run of the same cases records the real fixed/FastEmbed Demo defaults. The metrics deliberately separate retrieval, final evidence, forbidden leakage, routing, support-gate answerability, trace availability, and local latency. They reveal remaining selection and answerability failures rather than hiding them behind one accuracy number.
