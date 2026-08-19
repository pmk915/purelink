# PureLink RAG Generalization Eval Summary

## 1. Run Configuration

- Run id: `20260819-143232-auto-block_aware`
- Created at: `2026-08-19T14:32:32.767555+00:00`
- Commit: `c00a116`
- Dirty worktree: `True`
- Case file: `tests/eval/rag_generalization_cases.jsonl`
- Case count: 50
- Chunk strategy: `block_aware`
- Requested mode: `auto`
- Embedding: `local_hashed_bow` / `hashed_bow_v1`
- Reranker: `noop` enabled=False

## 2. Overall Metrics

| Metric | Value |
|---|---:|
| cases | 50 |
| retrieval_hit | 43 / 44 (97.7%) |
| citation_hit | 43 / 44 (97.7%) |
| expected_evidence_hit | 39 / 44 (88.6%) |
| forbidden_evidence_clean | 9 / 9 (100.0%) |
| router_accuracy | 50 / 50 (100.0%) |
| evidence-gate answerability_accuracy | 49 / 50 (98.0%) |
| mean_evidence_precision | 72.3% (n=42) |
| trace_available | 50 / 50 (100.0%) |

## 3. Metrics by Category

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `entity_attribute` | 7 | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 6 / 7 (85.7%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 73.8% (n=7) |
| `entity_definition` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 65.0% (n=8) |
| `entity_reason` | 6 | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 3 / 6 (50.0%) | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 44.0% (n=5) |
| `entity_relation` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 100.0% (n=8) |
| `no_answer` | 6 | n/a | n/a | n/a | 6 / 6 (100.0%) | 6 / 6 (100.0%) | n/a |
| `overview` | 5 | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 48.2% (n=5) |
| `technical` | 10 | 9 / 10 (90.0%) | 9 / 10 (90.0%) | 9 / 10 (90.0%) | 10 / 10 (100.0%) | 9 / 10 (90.0%) | 82.2% (n=9) |

## 4. Metrics by Selected Mode

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `chunk_only` | 30 | 23 / 24 (95.8%) | 23 / 24 (95.8%) | 19 / 24 (79.2%) | 30 / 30 (100.0%) | 29 / 30 (96.7%) | 62.6% (n=22) |
| `graph_vector_mix` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 100.0% (n=8) |
| `hybrid_text` | 7 | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 88.6% (n=7) |
| `overview` | 5 | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 48.2% (n=5) |

## 5. No-answer Results

| Case | predicted_answerable | evidence-gate answerability | forbidden_evidence_hit | failure_stage | failure_reasons |
|---|---:|---:|---:|---|---|
| `attr_deepseek_config` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_profit` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_ceo` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_ipo` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_processor` | False | true | false | `genuine_no_answer` | - |
| `no_answer_alice_birthday` | False | true | false | `genuine_no_answer` | - |

## 6. Latency Summary

In-process retrieval latency. Excludes ingestion, embedding/index construction, HTTP transport, LLM answer generation, and frontend rendering.

- mean: 11.1 ms
- p50: 11 ms
- p95: 16 ms
- max: 26 ms

## 7. Failure Diagnostics

### Stage Distribution

| Failure Stage | Cases |
|---|---:|
| `expected_phrase_format_mismatch` | 3 |
| `final_context_miss` | 1 |
| `genuine_no_answer` | 6 |
| `raw_candidate_miss` | 3 |
| `retrieval_document_miss` | 1 |
| `success` | 36 |

### Failed Cases

| Case | Question | Expected | Actual | Selected Mode | Failure Stage | Failure Reason |
|---|---|---|---|---|---|---|
| `attr_instance_state` | Python instance object 如何保存状态？ | stores per-object state, Instance attributes | Instantiation calls the class object like a function and creates a new instance object. If the class defines __init__, P; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | `final_context_miss` | expected_evidence_not_selected |
| `reason_python_classes` | Python 为什么使用 class？ | modeling many objects, separate state | Instantiation calls the class object like a function and creates a new instance object. If the class defines __init__, P; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | `raw_candidate_miss` | expected_evidence_not_selected |
| `reason_reprocess_old_docs` | 为什么旧 PureLink 文档需要重新处理？ | do not automatically receive new citation-unit behavior, reprocess the document and rebuild the vector index | Block-aware chunking uses document block boundaries and source spans so chunks better respect headings, pages, tables, a | `chunk_only` | `raw_candidate_miss` | expected_evidence_not_selected |
| `reason_low_score_refusal` | PureLink 为什么在低分证据时拒绝回答？ | Low-scoring or missing evidence can trigger, no-reliable-evidence response | Adaptation: concise paraphrase for deterministic PureLink evaluation; Adaptation: concise paraphrase for deterministic PureLink evaluation | `chunk_only` | `raw_candidate_miss` | expected_evidence_not_selected |
| `tech_text_file_types` | PureLink 支持哪些文本文件类型？ | Markdown-like text, Markdown, PDF, DOCX | - | `chunk_only` | `retrieval_document_miss` | expected_document_not_retrieved, expected_evidence_not_selected, unexpected_no_answer, citation_missing |

## 8. Known Limitations

- This baseline is deterministic and does not use LLM-as-judge.
- Evidence precision is approximated with expected/forbidden phrases and expected document names.
- Expected evidence phrase matching removes presentation-only Markdown and punctuation differences, but preserves numbers, identifiers, paths, and CLI flags.
- Evidence-gate answerability uses the production deterministic Evidence Support Gate, including query-type mandatory checks and support signals.
- Evidence support score is a debugging signal, not a semantic correctness score or LLM-as-judge result.
- No-answer failures expose limitations of the production support gate, not full QA accuracy.
- In-process retrieval latency is only useful for comparison on the same local environment.
- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.
