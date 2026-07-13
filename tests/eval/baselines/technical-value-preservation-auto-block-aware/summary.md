# PureLink RAG Generalization Eval Summary

## 1. Run Configuration

- Run id: `20260713-065601-auto-block_aware`
- Created at: `2026-07-13T06:56:01.781322+00:00`
- Commit: `4314bf2`
- Dirty worktree: `False`
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
| retrieval_hit | 42 / 45 (93.3%) |
| citation_hit | 42 / 45 (93.3%) |
| expected_evidence_hit | 32 / 45 (71.1%) |
| forbidden_evidence_clean | 7 / 9 (77.8%) |
| router_accuracy | 50 / 50 (100.0%) |
| evidence-gate answerability_accuracy | 50 / 50 (100.0%) |
| mean_evidence_precision | 30.9% (n=46) |
| trace_available | 50 / 50 (100.0%) |

## 3. Metrics by Category

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `entity_attribute` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 35.8% (n=8) |
| `entity_definition` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 42.5% (n=8) |
| `entity_reason` | 6 | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 3 / 6 (50.0%) | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 11.3% (n=6) |
| `entity_relation` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 61.3% (n=8) |
| `no_answer` | 5 | n/a | n/a | n/a | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 0.0% (n=1) |
| `overview` | 5 | 3 / 5 (60.0%) | 3 / 5 (60.0%) | 2 / 5 (40.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5.7% (n=5) |
| `technical` | 10 | 9 / 10 (90.0%) | 9 / 10 (90.0%) | 6 / 10 (60.0%) | 10 / 10 (100.0%) | 10 / 10 (100.0%) | 21.0% (n=10) |

## 4. Metrics by Selected Mode

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `chunk_only` | 30 | 24 / 25 (96.0%) | 24 / 25 (96.0%) | 19 / 25 (76.0%) | 30 / 30 (100.0%) | 30 / 30 (100.0%) | 31.3% (n=26) |
| `graph_vector_mix` | 8 | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 61.3% (n=8) |
| `hybrid_text` | 7 | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 4 / 7 (57.1%) | 7 / 7 (100.0%) | 7 / 7 (100.0%) | 12.9% (n=7) |
| `overview` | 5 | 3 / 5 (60.0%) | 3 / 5 (60.0%) | 2 / 5 (40.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5.7% (n=5) |

## 5. No-answer Results

| Case | retrieval_hit | citation_hit | expected_evidence_hit | predicted_answerable | evidence-gate answerability | forbidden_evidence_hit | failure_reasons |
|---|---:|---:|---:|---:|---:|---:|---|
| `no_answer_profit` | n/a | n/a | n/a | False | true | n/a | - |
| `no_answer_ceo` | n/a | n/a | n/a | False | true | n/a | - |
| `no_answer_ipo` | n/a | n/a | n/a | False | true | n/a | - |
| `no_answer_processor` | n/a | n/a | n/a | False | true | true | forbidden_evidence_selected |
| `no_answer_alice_birthday` | n/a | n/a | n/a | False | true | false | - |

## 6. Latency Summary

In-process retrieval latency. Excludes ingestion, embedding/index construction, HTTP transport, LLM answer generation, and frontend rendering.

- mean: 6.7 ms
- p50: 6 ms
- p95: 10 ms
- max: 22 ms

## 7. Failed Cases

| Case | Question | Expected | Actual | Selected Mode | Failure Reason |
|---|---|---|---|---|---|
| `def_python_class` | Python 类是什么？ | organizes data and behavior, user-defined type | Source basis: Python official documentation, Classes tutorial; Retrieved: 2026-07-11 | `chunk_only` | expected_evidence_not_selected |
| `attr_alice_location` | Alice Chen 在哪里办公？ | 办公地点：Singapore | 办公地点：Shanghai; 合作伙伴：Alice Chen | `chunk_only` | forbidden_evidence_selected |
| `attr_instance_state` | Python instance object 如何保存状态？ | stores per-object state, Instance attributes | Instantiation calls the class object like a function and creates a new instance object. If the class defines __init__, P; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | expected_evidence_not_selected |
| `reason_python_classes` | Python 为什么使用 class？ | modeling many objects, separate state | Instantiation calls the class object like a function and creates a new instance object. If the class defines __init__, P; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | expected_evidence_not_selected |
| `reason_reprocess_old_docs` | 为什么旧 PureLink 文档需要重新处理？ | do not automatically receive new citation-unit behavior, reprocess the document and rebuild the vector index | 特点：高性能; 颜色：黑色 | `chunk_only` | expected_evidence_not_selected |
| `reason_low_score_refusal` | PureLink 为什么在低分证据时拒绝回答？ | Low-scoring or missing evidence can trigger, no-reliable-evidence response | Adaptation: concise paraphrase for deterministic PureLink evaluation; Adaptation: concise paraphrase for deterministic PureLink evaluation | `chunk_only` | expected_evidence_not_selected |
| `rel_carol_group` | Carol Wang 属于哪个组？ | 隶属：Product Group | Carol Wang defines workspace workflows and collects user feedback. She belongs to the Product Group and translates produ; 角色：产品经理 | `graph_vector_mix` | expected_evidence_not_selected |
| `tech_chunk_strategy` | CHUNK_STRATEGY 支持哪些值？ | supports `fixed` and `block_aware` | PureLink supports fixed and block_aware chunk strategies. Fixed chunking creates character-based chunks.; Block-aware chunking uses document block boundaries and source spans so chunks better respect headings, pages, tables, a | `hybrid_text` | expected_evidence_not_selected |
| `tech_docker_down_v` | docker compose down -v 有什么影响？ | `docker compose down -v` removes volumes | docker compose down stops and removes containers while preserving named volumes unless volume deletion is requested. doc; PureLink supports fixed and block_aware chunk strategies. Fixed chunking creates character-based chunks. | `hybrid_text` | expected_evidence_not_selected |
| `tech_fastapi_depends` | FastAPI 中 Depends 的作用是什么？ | uses `Depends` to ask FastAPI | FastAPI includes dependency information in OpenAPI when it affects parameters or security. This allows generated API doc; An endpoint uses Depends to ask FastAPI to execute a dependency and pass the result into the path operation function. Th | `hybrid_text` | expected_evidence_not_selected |
| `tech_text_file_types` | PureLink 支持哪些文本文件类型？ | Markdown-like text, Markdown, PDF, DOCX | PureLink supports several retrieval modes. chunk_only performs vector retrieval over indexed chunks.; 颜色：黑色 | `chunk_only` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `overview_python_classes` | 总结 Python classes 文档 | Class Definition, Inheritance | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `overview` | expected_evidence_not_selected |
| `overview_fastapi_dependencies` | 概括 FastAPI dependencies 文档 | Dependency Injection, OpenAPI Integration | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `overview` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `overview_team_members` | 当前语料中的团队成员有哪些？ | Alice Chen, Bob Li, Carol Wang | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `overview` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `no_answer_processor` | Aurora Mini 的处理器型号是什么？ | - | Aurora Mini is the compact member of the Aurora catalog. It is designed for people who need a lightweight device that ca; 颜色：银色 | `chunk_only` | forbidden_evidence_selected |

## 8. Known Limitations

- This baseline is deterministic and does not use LLM-as-judge.
- Evidence precision is approximated with expected/forbidden phrases and expected document names.
- Evidence-gate answerability uses the production deterministic Evidence Support Gate, including query-type mandatory checks and support signals.
- Evidence support score is a debugging signal, not a semantic correctness score or LLM-as-judge result.
- No-answer failures expose limitations of the production support gate, not full QA accuracy.
- In-process retrieval latency is only useful for comparison on the same local environment.
- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.
