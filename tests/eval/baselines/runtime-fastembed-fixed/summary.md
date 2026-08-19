# PureLink RAG Generalization Eval Summary

## 1. Run Configuration

- Run id: `20260819-150435-auto-fixed`
- Created at: `2026-08-19T15:04:35.980952+00:00`
- Commit: `1bbcd65`
- Dirty worktree: `False`
- Case file: `tests/eval/rag_generalization_cases.jsonl`
- Case count: 50
- Chunk strategy: `fixed`
- Requested mode: `auto`
- Embedding: `fastembed` / `BAAI/bge-small-zh-v1.5`
- Reranker: `noop` enabled=False

## 2. Overall Metrics

| Metric | Value |
|---|---:|
| cases | 50 |
| retrieval_hit | 44 / 44 (100.0%) |
| citation_hit | 44 / 44 (100.0%) |
| expected_evidence_hit | 36 / 44 (81.8%) |
| forbidden_evidence_clean | 8 / 9 (88.9%) |
| router_accuracy | 50 / 50 (100.0%) |
| evidence-gate answerability_accuracy | 47 / 50 (94.0%) |
| mean_evidence_precision | 70.6% (n=41) |
| trace_available | 50 / 50 (100.0%) |

## 3. Metrics by Category

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `entity_attribute` | 7 | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 78.6% (n=7) |
| `entity_definition` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 6 / 8 (75.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 55.0% (n=8) |
| `entity_reason` | 6 | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 3 / 6 (50.0%) | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 75.0% (n=4) |
| `entity_relation` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 6 / 8 (75.0%) | 87.5% (n=8) |
| `no_answer` | 6 | n/a | n/a | n/a | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 0.0% (n=1) |
| `overview` | 5 | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 47.9% (n=5) |
| `technical` | 10 | 10 / 10 (100.0%) | 10 / 10 (100.0%) | 8 / 10 (80.0%) | 10 / 10 (100.0%) | 9 / 10 (90.0%) | 83.3% (n=8) |

## 4. Metrics by Selected Mode

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `chunk_only` | 30 | 24 / 24 (100.0%) | 24 / 24 (100.0%) | 19 / 24 (79.2%) | 30 / 30 (100.0%) | 30 / 30 (100.0%) | 66.2% (n=23) |
| `graph_vector_mix` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 6 / 8 (75.0%) | 87.5% (n=8) |
| `hybrid_text` | 7 | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 5 / 7 (71.4%) | 7 / 7 (100.0%) | 6 / 7 (85.7%) | 86.7% (n=5) |
| `overview` | 5 | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 47.9% (n=5) |

## 5. No-answer Results

| Case | predicted_answerable | evidence-gate answerability | forbidden_evidence_hit | failure_stage | failure_reasons |
|---|---:|---:|---:|---|---|
| `attr_deepseek_config` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_profit` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_ceo` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_ipo` | False | true | n/a | `genuine_no_answer` | - |
| `no_answer_processor` | False | true | false | `genuine_no_answer` | - |
| `no_answer_alice_birthday` | False | true | true | `genuine_no_answer` | forbidden_evidence_selected |

## 6. Latency Summary

In-process retrieval latency. Excludes ingestion, embedding/index construction, HTTP transport, LLM answer generation, and frontend rendering.

- mean: 24.1 ms
- p50: 24 ms
- p95: 33 ms
- max: 39 ms

## 7. Failure Diagnostics

### Stage Distribution

| Failure Stage | Cases |
|---|---:|
| `evidence_selection_miss` | 7 |
| `expected_phrase_format_mismatch` | 2 |
| `genuine_no_answer` | 6 |
| `raw_candidate_miss` | 1 |
| `success` | 33 |
| `support_gate_miss` | 1 |

### Failed Cases

| Case | Question | Expected | Actual | Selected Mode | Failure Stage | Failure Reason |
|---|---|---|---|---|---|---|
| `def_alice` | Alice 是谁？ | central child character | These relationships are not equal friendships; they are story encounters that move Alice through Wonderland.; 角色：检索工程师 | `chunk_only` | `evidence_selection_miss` | expected_evidence_not_selected |
| `def_retrieval_trace` | PureLink retrieval trace 是什么？ | records candidate and final evidence metadata, selected mode | Trace availability is an evaluation metric because it confirms observable diagnostics.; graph_vector_mix is used for relation-oriented questions. It retrieves lightweight graph candidates and merges them with | `chunk_only` | `evidence_selection_miss` | expected_evidence_not_selected |
| `reason_fastapi_di` | FastAPI 为什么使用 dependency injection？ | keeps route functions focused, shared concerns stay in small functions | FastAPI includes dependency information in OpenAPI when it affects parameters or security. This allows generated API doc | `chunk_only` | `evidence_selection_miss` | expected_evidence_not_selected |
| `reason_reprocess_old_docs` | 为什么旧 PureLink 文档需要重新处理？ | do not automatically receive new citation-unit behavior, reprocess the document and rebuild the vector index | It is useful for questions about dependencies, ownership, permissions, source-target links, and entity relationships.; Block-aware chunking uses document block boundaries and source spans so chunks better respect headings, pages, tables, a | `chunk_only` | `evidence_selection_miss` | expected_evidence_not_selected |
| `reason_low_score_refusal` | PureLink 为什么在低分证据时拒绝回答？ | Low-scoring or missing evidence can trigger, no-reliable-evidence response | It is useful for questions about dependencies, ownership, permissions, source-target links, and entity relationships. | `chunk_only` | `raw_candidate_miss` | expected_evidence_not_selected |
| `rel_endpoint_dependency` | endpoint 和 dependency 是什么关系？ | endpoint uses `Depends`, pass the result into the path operation | FastAPI dependency injection lets an endpoint declare reusable requirements instead of creating every object directly in; Nested dependencies make it possible to build layered behavior, such as authentication that relies on token parsing and  | `graph_vector_mix` | `evidence_selection_miss` | expected_evidence_not_selected, unexpected_no_answer |
| `rel_class_instance` | class 和 instance 是什么关系？ | class object supports attribute reference and instantiation, creates a new instance object | A class definition creates a class object, not an instance. The class body can define methods, constants, and other attr; Instantiation calls the class object like a function and creates a new instance object. If the class defines __init__, P | `graph_vector_mix` | `support_gate_miss` | unexpected_no_answer |
| `tech_fastapi_depends` | FastAPI 中 Depends 的作用是什么？ | uses `Depends` to ask FastAPI | FastAPI dependency injection lets an endpoint declare reusable requirements instead of creating every object directly in; A dependency is usually a callable that receives request data or other dependencies and returns a value for the endpoint | `hybrid_text` | `evidence_selection_miss` | expected_evidence_not_selected, unexpected_no_answer |
| `tech_python_init` | __init__ 在什么时候调用？ | Python calls it during instantiation | A Python class is a user-defined type that organizes data and behavior together. It acts as a namespace for attributes a; A class definition creates a class object, not an instance. The class body can define methods, constants, and other attr | `hybrid_text` | `evidence_selection_miss` | expected_evidence_not_selected |
| `no_answer_alice_birthday` | Alice Chen 的生日是什么？ | - | 角色：检索工程师 | `chunk_only` | `genuine_no_answer` | forbidden_evidence_selected |

## 8. Known Limitations

- This baseline is deterministic and does not use LLM-as-judge.
- Evidence precision is approximated with expected/forbidden phrases and expected document names.
- Expected evidence phrase matching removes presentation-only Markdown and punctuation differences, but preserves numbers, identifiers, paths, and CLI flags.
- Evidence-gate answerability uses the production deterministic Evidence Support Gate, including query-type mandatory checks and support signals.
- Evidence support score is a debugging signal, not a semantic correctness score or LLM-as-judge result.
- No-answer failures expose limitations of the production support gate, not full QA accuracy.
- In-process retrieval latency is only useful for comparison on the same local environment.
- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.
