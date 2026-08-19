# Evaluation and Failure Analysis

## Scope

PureLink has one current official interview regression suite: 50 deterministic cases over nine small cross-domain documents. There are 44 answerable and 6 no-answer cases. The suite uses the real ingestion, indexing, AUTO routing, retrieval, evidence selection, production Evidence Support, Answer Policy metadata, citation readiness, and trace path.

The runner does not use LLM-as-judge. Expected/forbidden phrases and expected documents approximate evidence quality; they do not prove semantic correctness or production generalization.

## Two Questions, Two Snapshots

The deterministic regression snapshot uses block-aware chunking, local hashed BoW, no reranker, and AUTO. It answers: “Did a code change cause regression?”

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

The default Runtime snapshot uses fixed chunking, FastEmbed `BAAI/bge-small-zh-v1.5`, no reranker, and AUTO. It answers: “How does the actual Demo default perform?”

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

Do not present FastEmbed as automatically superior or hashed BoW as the user-facing model. The former describes runtime defaults; the latter provides low-dependency repeatability.

## Failure Boundaries

The report records raw-candidate, final-context, canonical-selection, support-gate, and phrase-format stages. This lets one failed question be diagnosed as:

```text
routing → retrieval → context selection → evidence selection → support → policy
```

`RetrievalResult.evidences` is canonical final evidence. Raw candidates and intermediate chunks remain diagnostics and do not receive final evidence credit.

The support-aware narrowing step applies only when the deterministic gate identifies explicit supporting IDs for entity attributes, exact technical identifiers, or entity relations. Overview and generic factual questions retain breadth. Unsupported questions retain diagnostic evidence, but Answer Policy skips the provider and returns no citations.

## Holdout Decision

Before narrowing, the current code produced 67.3% deterministic evidence precision. After narrowing it produced 72.3%, while retrieval/citation stayed 43/44, expected evidence stayed 39/44, forbidden clean stayed 9/9, router stayed 50/50, and answerability stayed 49/50.

The independent 20-case holdout did not change:

- retrieval/citation: 16 / 16
- expected evidence: 13 / 16
- forbidden clean: 12 / 12
- router, answerability, and trace: 20 / 20
- mean evidence precision: 100% over 13 applicable cases

That is why the narrowing was retained. It improved precision without a holdout or no-answer regression and did not add case-specific retrieval rules.

## Reproduce

```bash
make eval-rag-generalization
make eval-rag-generalization-holdout
make eval-rag-runtime
```

Runner: [`run_rag_generalization_eval.py`](../../../scripts/eval/run_rag_generalization_eval.py). Cases: [`rag_generalization_cases.jsonl`](../../../tests/eval/rag_generalization_cases.jsonl). Metric and snapshot rendering: [`rag_generalization.py`](../../../scripts/eval/rag_generalization.py).

The historical 20-case repository-doc comparison is retained for provenance, but it is not a current result or release gate.

## Interview Framing

> “I evaluate the real processing and retrieval path with one 50-case cross-domain suite. I keep deterministic regression separate from the actual FastEmbed Runtime snapshot, and I measure retrieval, canonical evidence, forbidden leakage, routing, support-gate answerability, citations, traces, and local latency separately. The reports preserve known failures, because the purpose is to locate regressions and explain trade-offs—not to manufacture one flattering accuracy number.”
