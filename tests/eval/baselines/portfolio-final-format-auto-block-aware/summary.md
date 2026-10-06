# PureLink RAG Format Eval Summary

## 1. Run Configuration

- Run id: `format-20261006-144009-auto-block_aware`
- Created at: `2026-10-06T14:40:09.979401+00:00`
- Commit: `c25c7c3`
- Dirty worktree: `True`
- Case file: `tests/eval/rag_format_cases.jsonl`
- Case count: 24
- Chunk strategy: `block_aware`
- Requested mode: `auto`
- Embedding: `local_hashed_bow` / `hashed_bow_v1`
- Reranker: `noop` enabled=False

## 2. Overall Metrics

| Metric | Value |
|---|---:|
| cases | 24 |
| document_recall_at_1 | 85.0% (n=20) |
| document_recall_at_3 | 100.0% (n=20) |
| document_recall_at_5 | 100.0% (n=20) |
| document_mrr | 0.925 (n=20) |
| retrieval_hit | 20 / 20 (100.0%) |
| citation_hit | 20 / 20 (100.0%) |
| expected_evidence_hit | 20 / 20 (100.0%) |
| evidence_recall | 100.0% (n=20) |
| forbidden_evidence_clean | 9 / 16 (56.2%) |
| router_accuracy | n/a |
| evidence-gate answerability_accuracy | 24 / 24 (100.0%) |
| mean_evidence_precision | 72.5% (n=20) |
| trace_available | 24 / 24 (100.0%) |
| page_provenance_hit | 2 / 2 (100.0%) |

## 3. Metrics by Category

| Group | Cases | recall@5 | MRR | retrieval_hit | citation_hit | expected_evidence_hit | evidence_recall | router_accuracy | evidence-gate answerability | evidence_precision | page_provenance_hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `distractor_sensitive` | 4 | 100.0% (n=4) | 1.000 (n=4) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 100.0% (n=4) | n/a | 4 / 4 (100.0%) | 75.0% (n=4) | 1 / 1 (100.0%) |
| `factual_lookup` | 4 | 100.0% (n=4) | 1.000 (n=4) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 100.0% (n=4) | n/a | 4 / 4 (100.0%) | 50.0% (n=4) | n/a |
| `no_answer` | 4 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 4 / 4 (100.0%) | n/a | n/a |
| `section_scoped` | 4 | 100.0% (n=4) | 0.625 (n=4) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 100.0% (n=4) | n/a | 4 / 4 (100.0%) | 100.0% (n=4) | n/a |
| `structured_fact` | 4 | 100.0% (n=4) | 1.000 (n=4) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 100.0% (n=4) | n/a | 4 / 4 (100.0%) | 37.5% (n=4) | 1 / 1 (100.0%) |
| `technical` | 4 | 100.0% (n=4) | 1.000 (n=4) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 100.0% (n=4) | n/a | 4 / 4 (100.0%) | 100.0% (n=4) | n/a |

## 4. Metrics by Selected Mode

| Group | Cases | recall@5 | MRR | retrieval_hit | citation_hit | expected_evidence_hit | evidence_recall | router_accuracy | evidence-gate answerability | evidence_precision | page_provenance_hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `chunk_only` | 20 | 100.0% (n=16) | 0.906 (n=16) | 16 / 16 (100.0%) | 16 / 16 (100.0%) | 16 / 16 (100.0%) | 100.0% (n=16) | n/a | 20 / 20 (100.0%) | 65.6% (n=16) | 2 / 2 (100.0%) |
| `hybrid_text` | 4 | 100.0% (n=4) | 1.000 (n=4) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 4 / 4 (100.0%) | 100.0% (n=4) | n/a | 4 / 4 (100.0%) | 100.0% (n=4) | n/a |

## 5. No-answer Results

| Case | predicted_answerable | evidence-gate answerability | forbidden_evidence_hit | failure_stage | failure_reasons |
|---|---:|---:|---:|---|---|
| `txt_no_answer` | False | true | n/a | `genuine_no_answer` | - |
| `markdown_no_answer` | False | true | n/a | `genuine_no_answer` | - |
| `docx_no_answer` | False | true | n/a | `genuine_no_answer` | - |
| `pdf_no_answer` | False | true | n/a | `genuine_no_answer` | - |

## 6. Latency Summary

In-process retrieval latency excludes ingestion, index construction, QA, HTTP transport, and frontend rendering. Total eval includes retrieval and heuristic QA; it excludes ingestion, index construction, and metric evaluation.

| Stage | mean (ms) | p50 (ms) | p95 (ms) | max (ms) | n |
|---|---:|---:|---:|---:|---:|
| retrieval | 7.9 | 7 | 13 | 29 | 24 |
| total eval | 10.1 | 8 | 18 | 31 | 24 |

## 7. Failure Diagnostics

### Stage Distribution

| Failure Stage | Cases |
|---|---:|
| `genuine_no_answer` | 4 |
| `success` | 20 |

### Failed Cases

| Case | Question | Expected | Actual | Selected Mode | Failure Stage | Failure Reason |
|---|---|---|---|---|---|---|
| `txt_factual_lookup` | Who maintains the current Cedar runtime? | Cedar is maintained by Mira Chen | Cedar is maintained by Mira Chen.; CEDAR_RETRY_LIMIT defaults to 2 retries in the archived Cedar runtime. Cedar was previously maintained by Rowan Lee. | `chunk_only` | `success` | forbidden_evidence_selected |
| `txt_structured_fact` | How much memory is reserved by the compact profile in Cedar? | 384 MiB | \| Profile \| Reserved memory \| \| --- \| --- \| \| Cedar compact \| 384 MiB \| \| Cedar standard \| 768 MiB \| | `chunk_only` | `success` | forbidden_evidence_selected |
| `markdown_factual_lookup` | Who maintains the current Maple runtime? | Maple is maintained by Mira Chen | Maple is maintained by Mira Chen.; MAPLE_RETRY_LIMIT defaults to 2 retries in the archived Maple runtime. Maple was previously maintained by Rowan Lee. | `chunk_only` | `success` | forbidden_evidence_selected |
| `markdown_structured_fact` | How much memory is reserved by the compact profile in Maple? | 384 MiB | \| Profile \| Reserved memory \| \| --- \| --- \| \| Maple compact \| 384 MiB \| \| Maple standard \| 768 MiB \| | `chunk_only` | `success` | forbidden_evidence_selected |
| `docx_factual_lookup` | Who maintains the current Birch runtime? | Birch is maintained by Mira Chen | Birch is maintained by Mira Chen.; Birch was previously maintained by Rowan Lee. | `chunk_only` | `success` | forbidden_evidence_selected |
| `pdf_factual_lookup` | Who maintains the current Aspen runtime? | Aspen is maintained by Mira Chen | Aspen is maintained by Mira Chen.; Aspen was previously maintained by Rowan Lee. | `chunk_only` | `success` | forbidden_evidence_selected |
| `pdf_structured_fact` | How much memory is reserved by the compact profile in Aspen? | 384 MiB | Aspen compact profile memory: 384 MiB.; \| Profile \| Reserved memory \| \| --- \| --- \| \| Cedar compact \| 384 MiB \| \| Cedar standard \| 768 MiB \| | `chunk_only` | `success` | forbidden_evidence_selected |

## 8. Known Limitations

- This baseline is deterministic and does not use LLM-as-judge.
- Document Recall@K and MRR use distinct documents in initial_chunks order, before context/evidence selection; they do not rank citations.
- Evidence recall counts distinct normalized expected phrases in canonical final evidence; no-answer cases are excluded.
- Evidence precision is approximated with expected/forbidden phrases and expected document names.
- Expected evidence phrase matching removes presentation-only Markdown and punctuation differences, but preserves numbers, identifiers, paths, and CLI flags.
- Evidence-gate answerability uses the production deterministic Evidence Support Gate, including query-type mandatory checks and support signals.
- Evidence support score is a debugging signal, not a semantic correctness score or LLM-as-judge result.
- No-answer failures expose limitations of the production support gate, not full QA accuracy.
- In-process retrieval latency is only useful for comparison on the same local environment.
- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.
- The legacy success stage means expected evidence survived and passed support checks; forbidden evidence or low precision can still be present. Review failure reasons and precision separately.

## 9. Metrics by Document Format

| Group | Cases | recall@5 | MRR | retrieval_hit | citation_hit | expected_evidence_hit | evidence_recall | router_accuracy | evidence-gate answerability | evidence_precision | page_provenance_hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `docx` | 6 | 100.0% (n=5) | 0.900 (n=5) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 100.0% (n=5) | n/a | 6 / 6 (100.0%) | 90.0% (n=5) | n/a |
| `markdown` | 6 | 100.0% (n=5) | 0.900 (n=5) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 100.0% (n=5) | n/a | 6 / 6 (100.0%) | 70.0% (n=5) | n/a |
| `pdf` | 6 | 100.0% (n=5) | 1.000 (n=5) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 100.0% (n=5) | n/a | 6 / 6 (100.0%) | 70.0% (n=5) | 2 / 2 (100.0%) |
| `txt` | 6 | 100.0% (n=5) | 0.900 (n=5) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 100.0% (n=5) | n/a | 6 / 6 (100.0%) | 60.0% (n=5) | n/a |
