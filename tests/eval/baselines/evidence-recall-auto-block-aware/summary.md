# PureLink RAG Generalization Eval Summary

## 1. Run Configuration

- Run id: `20260712-103622-auto-block_aware`
- Created at: `2026-07-12T10:36:22.612868+00:00`
- Commit: `327b186`
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
| citation_hit | 26 / 45 (57.8%) |
| expected_evidence_hit | 30 / 45 (66.7%) |
| forbidden_evidence_clean | 7 / 9 (77.8%) |
| router_accuracy | 50 / 50 (100.0%) |
| evidence-gate answerability_accuracy | 49 / 50 (98.0%) |
| mean_evidence_precision | 31.8% (n=44) |
| trace_available | 50 / 50 (100.0%) |

## 3. Metrics by Category

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `entity_attribute` | 8 | 8 / 8 (100.0%) | 5 / 8 (62.5%) | 6 / 8 (75.0%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 28.1% (n=7) |
| `entity_definition` | 8 | 8 / 8 (100.0%) | 4 / 8 (50.0%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 52.5% (n=8) |
| `entity_reason` | 6 | 6 / 6 (100.0%) | 0 / 6 (0.0%) | 3 / 6 (50.0%) | 6 / 6 (100.0%) | 6 / 6 (100.0%) | 12.5% (n=6) |
| `entity_relation` | 8 | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 62.9% (n=8) |
| `no_answer` | 5 | n/a | n/a | n/a | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 0.0% (n=1) |
| `overview` | 5 | 3 / 5 (60.0%) | 3 / 5 (60.0%) | 2 / 5 (40.0%) | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 5.7% (n=5) |
| `technical` | 10 | 9 / 10 (90.0%) | 7 / 10 (70.0%) | 5 / 10 (50.0%) | 10 / 10 (100.0%) | 9 / 10 (90.0%) | 19.4% (n=9) |

## 4. Metrics by Selected Mode

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `chunk_only` | 30 | 24 / 25 (96.0%) | 11 / 25 (44.0%) | 18 / 25 (72.0%) | 30 / 30 (100.0%) | 30 / 30 (100.0%) | 32.5% (n=25) |
| `graph_vector_mix` | 8 | 8 / 8 (100.0%) | 7 / 8 (87.5%) | 7 / 8 (87.5%) | 8 / 8 (100.0%) | 8 / 8 (100.0%) | 62.9% (n=8) |
| `hybrid_text` | 7 | 7 / 7 (100.0%) | 5 / 7 (71.4%) | 3 / 7 (42.9%) | 7 / 7 (100.0%) | 6 / 7 (85.7%) | 9.0% (n=6) |
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

- mean: 6.8 ms
- p50: 6 ms
- p95: 8 ms
- max: 23 ms

## 7. Failed Cases

| Case | Question | Expected | Actual | Selected Mode | Failure Reason |
|---|---|---|---|---|---|
| `def_python_class` | Python 类是什么？ | organizes data and behavior, user-defined type | Source basis: Python official documentation, Classes tutorial  Adaptation: concise paraphrase for deterministic PureLink; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `def_postgres_mvcc` | PostgreSQL MVCC 是什么？ | multiversion concurrency control, snapshot of rows | Source basis: PostgreSQL official documentation, MVCC and locking  Adaptation: concise paraphrase for deterministic Pure; PostgreSQL uses multiversion concurrency control, or MVCC, so readers and writers can often operate without blocking eac | `chunk_only` | citation_missing |
| `def_aurora_pro` | Aurora Pro 是什么产品？ | performance-oriented model, local model inference | 角色：产品经理  办公地点：Beijing  负责：知识库工作台和用户研究  隶属：Product Group  Carol Wang defines workspace workflows and collects user feedba; 颜色：黑色  重量：2.1 kg  特点：高性能  适用场景：本地模型推理  Aurora Pro is the performance-oriented model. It is heavier than the Mini and Air | `chunk_only` | citation_missing |
| `def_retrieval_trace` | PureLink retrieval trace 是什么？ | records candidate and final evidence metadata, selected mode | Source basis: PureLink retrieval and citation documentation  Adaptation: concise project-specific facts for deterministi; Retrieval trace records candidate and final evidence metadata, the selected mode, router reason, reranker usage, and cou | `chunk_only` | citation_missing |
| `attr_alice_location` | Alice Chen 在哪里办公？ | 办公地点：Singapore | 办公地点：Shanghai; 合作伙伴：Alice Chen | `chunk_only` | forbidden_evidence_selected |
| `attr_aurora_pro_weight` | Aurora Pro 重量是多少？ | 重量：2.1 kg | 重量：2. 1 kg | `chunk_only` | expected_evidence_not_selected |
| `attr_cheshire_cat` | Cheshire Cat 有什么特点？ | grin and its ability to vanish, leaving the smile visible | The Cheshire Cat is known for its grin and its ability to vanish. It can disappear gradually while leaving the smile vis; 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w | `chunk_only` | citation_missing |
| `attr_instance_state` | Python instance object 如何保存状态？ | stores per-object state, Instance attributes | Instantiation calls the class object like a function and creates a new instance object. If the class defines init, Pytho; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | expected_evidence_not_selected |
| `attr_deepseek_config` | DeepSeek API 配置位于哪里？ | API paths, environment variables, code-like tokens | hybridtext helps with API paths, environment variables, code-like tokens, file names, commands, and other exact text. It; Source basis: Project Gutenberg edition of Alice's Adventures in Wonderland  Adaptation: concise character facts for det | `chunk_only` | citation_missing |
| `attr_block_aware_features` | block_aware 有什么特点？ | uses document block boundaries and source spans, respect headings | PureLink supports fixed and blockaware chunk strategies. Fixed chunking creates character-based chunks. Block-aware chun; 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w | `chunk_only` | citation_missing |
| `reason_python_classes` | Python 为什么使用 class？ | modeling many objects, separate state | After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads; A Python class is a user-defined type that organizes data and behavior together. It acts as a namespace for attributes a | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `reason_fastapi_di` | FastAPI 为什么使用 dependency injection？ | keeps route functions focused, shared concerns stay in small functions | FastAPI dependency injection lets an endpoint declare reusable requirements instead of creating every object directly in; A dependency can depend on another dependency. FastAPI resolves this tree and reuses results where appropriate during on | `chunk_only` | citation_missing |
| `reason_postgres_mvcc` | PostgreSQL 为什么使用 MVCC？ | readers and writers can often operate without blocking, preserve consistency | Source basis: PostgreSQL official documentation, MVCC and locking  Adaptation: concise paraphrase for deterministic Pure; PostgreSQL uses multiversion concurrency control, or MVCC, so readers and writers can often operate without blocking eac | `chunk_only` | citation_missing |
| `reason_aurora_mini_mobile` | Aurora Mini 为什么适合移动办公？ | 特点：便携, 适用场景：移动办公 | 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w; 角色：产品经理  办公地点：Beijing  负责：知识库工作台和用户研究  隶属：Product Group  Carol Wang defines workspace workflows and collects user feedba | `chunk_only` | citation_missing |
| `reason_reprocess_old_docs` | 为什么旧 PureLink 文档需要重新处理？ | do not automatically receive new citation-unit behavior, reprocess the document and rebuild the vector index | 颜色：黑色  重量：2.1 kg  特点：高性能  适用场景：本地模型推理  Aurora Pro is the performance-oriented model. It is heavier than the Mini and Air; Source basis: FastAPI official documentation, Dependencies tutorial  Adaptation: concise paraphrase for deterministic Pu | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `reason_low_score_refusal` | PureLink 为什么在低分证据时拒绝回答？ | Low-scoring or missing evidence can trigger, no-reliable-evidence response | Source basis: FastAPI official documentation, Dependencies tutorial  Adaptation: concise paraphrase for deterministic Pu; Source basis: Python official documentation, Classes tutorial  Adaptation: concise paraphrase for deterministic PureLink | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `rel_carol_group` | Carol Wang 属于哪个组？ | 隶属：Product Group | Carol Wang defines workspace workflows and collects user feedback. She belongs to the Product Group and translates produ; 角色：产品经理 | `graph_vector_mix` | expected_evidence_not_selected |
| `rel_endpoint_dependency` | endpoint 和 dependency 是什么关系？ | endpoint uses `Depends`, pass the result into the path operation | An endpoint uses Depends to ask FastAPI to execute a dependency and pass the result into the path operation function. Th; FastAPI dependency injection lets an endpoint declare reusable requirements instead of creating every object directly in | `graph_vector_mix` | citation_missing |
| `tech_retrieval_min_score` | RETRIEVAL_MIN_SCORE 默认值是什么？ | `RETRIEVAL_MIN_SCORE` configures | RETRIEVALMINSCORE configures the minimum retrieval score used by answer generation reliability checks. Low-scoring or mi; Source basis: PureLink retrieval and citation documentation | `hybrid_text` | expected_evidence_not_selected, unexpected_no_answer |
| `tech_chunk_strategy` | CHUNK_STRATEGY 支持哪些值？ | supports `fixed` and `block_aware` | PureLink supports fixed and blockaware chunk strategies. Fixed chunking creates character-based chunks.; Block-aware chunking uses document block boundaries and source spans so chunks better respect headings, pages, tables, a | `hybrid_text` | expected_evidence_not_selected |
| `tech_docker_down_v` | docker compose down -v 有什么影响？ | `docker compose down -v` removes volumes | docker compose down stops and removes containers while preserving named volumes unless volume deletion is requested. doc; PureLink supports fixed and blockaware chunk strategies. Fixed chunking creates character-based chunks. | `hybrid_text` | expected_evidence_not_selected |
| `tech_fastapi_depends` | FastAPI 中 Depends 的作用是什么？ | uses `Depends` to ask FastAPI | FastAPI includes dependency information in OpenAPI when it affects parameters or security. This allows generated API doc; An endpoint uses Depends to ask FastAPI to execute a dependency and pass the result into the path operation function. Th | `hybrid_text` | expected_evidence_not_selected, citation_missing |
| `tech_graph_vector_mix` | graph_vector_mix 的用途是什么？ | used for relation-oriented questions, merges them with vector chunks | PureLink supports several retrieval modes. chunkonly performs vector retrieval over indexed chunks. overview collects br; graphvectormix is used for relation-oriented questions. It retrieves lightweight graph candidates and merges them with v | `hybrid_text` | citation_missing |
| `tech_text_file_types` | PureLink 支持哪些文本文件类型？ | Markdown-like text, Markdown, PDF, DOCX | 颜色：黑色; 重量：2. 1 kg | `chunk_only` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `overview_python_classes` | 总结 Python classes 文档 | Class Definition, Inheritance | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `overview` | expected_evidence_not_selected |
| `overview_fastapi_dependencies` | 概括 FastAPI dependencies 文档 | Dependency Injection, OpenAPI Integration | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `overview` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `overview_team_members` | 当前语料中的团队成员有哪些？ | Alice Chen, Bob Li, Carol Wang | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `overview` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `no_answer_processor` | Aurora Mini 的处理器型号是什么？ | - | 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w; 颜色：灰色  重量：8.5 kg  特点：可扩展  适用场景：团队部署  Aurora Server is a team deployment device. It is much heavier than the portable mod | `chunk_only` | forbidden_evidence_selected |

## 8. Known Limitations

- This baseline is deterministic and does not use LLM-as-judge.
- Evidence precision is approximated with expected/forbidden phrases and expected document names.
- Evidence-gate answerability uses the production deterministic Evidence Support Gate, including query-type mandatory checks and support signals.
- Evidence support score is a debugging signal, not a semantic correctness score or LLM-as-judge result.
- No-answer failures expose limitations of the production support gate, not full QA accuracy.
- In-process retrieval latency is only useful for comparison on the same local environment.
- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.
