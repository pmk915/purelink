# PureLink RAG Generalization Eval Summary

## 1. Run Configuration

- Run id: `20260711-172902-auto-block_aware`
- Created at: `2026-07-11T17:29:02.895199+00:00`
- Commit: `066819e`
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
| retrieval_hit | 41 / 45 (91.1%) |
| citation_hit | 19 / 45 (42.2%) |
| expected_evidence_hit | 22 / 45 (48.9%) |
| forbidden_evidence_clean | 6 / 9 (66.7%) |
| router_accuracy | 35 / 50 (70.0%) |
| evidence-gate answerability_accuracy | 45 / 50 (90.0%) |
| mean_evidence_precision | 24.0% (n=45) |
| trace_available | 50 / 50 (100.0%) |

## 3. Metrics by Category

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `entity_attribute` | 8 | 7 / 8 (87.5%) | 4 / 8 (50.0%) | 5 / 8 (62.5%) | 6 / 8 (75.0%) | 8 / 8 (100.0%) | 22.1% (n=8) |
| `entity_definition` | 8 | 8 / 8 (100.0%) | 4 / 8 (50.0%) | 6 / 8 (75.0%) | 5 / 8 (62.5%) | 8 / 8 (100.0%) | 58.8% (n=8) |
| `entity_reason` | 6 | 6 / 6 (100.0%) | 0 / 6 (0.0%) | 2 / 6 (33.3%) | 4 / 6 (66.7%) | 6 / 6 (100.0%) | 8.3% (n=6) |
| `entity_relation` | 8 | 8 / 8 (100.0%) | 2 / 8 (25.0%) | 4 / 8 (50.0%) | 6 / 8 (75.0%) | 8 / 8 (100.0%) | 22.3% (n=8) |
| `no_answer` | 5 | n/a | n/a | n/a | 4 / 5 (80.0%) | 0 / 5 (0.0%) | 0.0% (n=1) |
| `overview` | 5 | 4 / 5 (80.0%) | 4 / 5 (80.0%) | 2 / 5 (40.0%) | 3 / 5 (60.0%) | 5 / 5 (100.0%) | 12.9% (n=5) |
| `technical` | 10 | 8 / 10 (80.0%) | 5 / 10 (50.0%) | 3 / 10 (30.0%) | 7 / 10 (70.0%) | 10 / 10 (100.0%) | 15.6% (n=9) |

## 4. Metrics by Selected Mode

| Group | Cases | retrieval_hit | citation_hit | expected_evidence_hit | router_accuracy | evidence-gate answerability | evidence_precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| `chunk_only` | 23 | 18 / 19 (94.7%) | 9 / 19 (47.4%) | 10 / 19 (52.6%) | 22 / 23 (95.7%) | 19 / 23 (82.6%) | 25.7% (n=20) |
| `graph_vector_mix` | 10 | 9 / 10 (90.0%) | 4 / 10 (40.0%) | 4 / 10 (40.0%) | 6 / 10 (60.0%) | 10 / 10 (100.0%) | 25.8% (n=10) |
| `hybrid_text` | 14 | 12 / 13 (92.3%) | 4 / 13 (30.8%) | 7 / 13 (53.8%) | 4 / 14 (28.6%) | 13 / 14 (92.9%) | 24.4% (n=12) |
| `overview` | 3 | 2 / 3 (66.7%) | 2 / 3 (66.7%) | 1 / 3 (33.3%) | 3 / 3 (100.0%) | 3 / 3 (100.0%) | 4.8% (n=3) |

## 5. No-answer Results

| Case | retrieval_hit | citation_hit | expected_evidence_hit | predicted_answerable | evidence-gate answerability | forbidden_evidence_hit | failure_reasons |
|---|---:|---:|---:|---:|---:|---:|---|
| `no_answer_profit` | n/a | n/a | n/a | True | false | n/a | unexpected_answerable |
| `no_answer_ceo` | n/a | n/a | n/a | True | false | n/a | router_mode_mismatch, unexpected_answerable |
| `no_answer_ipo` | n/a | n/a | n/a | True | false | n/a | unexpected_answerable |
| `no_answer_processor` | n/a | n/a | n/a | True | false | true | forbidden_evidence_selected, unexpected_answerable |
| `no_answer_alice_birthday` | n/a | n/a | n/a | True | false | false | unexpected_answerable |

## 6. Latency Summary

In-process retrieval latency. Excludes ingestion, embedding/index construction, HTTP transport, LLM answer generation, and frontend rendering.

- mean: 6.4 ms
- p50: 6 ms
- p95: 8 ms
- max: 19 ms

## 7. Failed Cases

| Case | Question | Expected | Actual | Selected Mode | Failure Reason |
|---|---|---|---|---|---|
| `def_python_class` | Python 类是什么？ | organizes data and behavior, user-defined type | Source basis: Python official documentation, Classes tutorial  Adaptation: concise paraphrase for deterministic PureLink; Deadlocks can occur when transactions wait on each other in a cycle. PostgreSQL detects deadlocks and cancels one transa | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `def_fastapi_dependency` | FastAPI dependency 是什么？ | declare reusable requirements, dependency is usually a callable | FastAPI dependency injection lets an endpoint declare reusable requirements instead of creating every object directly in | `graph_vector_mix` | router_mode_mismatch |
| `def_postgres_mvcc` | PostgreSQL MVCC 是什么？ | multiversion concurrency control, snapshot of rows | PostgreSQL uses multiversion concurrency control, or MVCC, so readers and writers can often operate without blocking eac; Source basis: PostgreSQL official documentation, MVCC and locking  Adaptation: concise paraphrase for deterministic Pure | `hybrid_text` | router_mode_mismatch, citation_missing |
| `def_aurora_pro` | Aurora Pro 是什么产品？ | performance-oriented model, local model inference | 角色：产品经理  办公地点：Beijing  负责：知识库工作台和用户研究  隶属：Product Group  Carol Wang defines workspace workflows and collects user feedba; Deadlocks can occur when transactions wait on each other in a cycle. PostgreSQL detects deadlocks and cancels one transa | `chunk_only` | citation_missing |
| `def_retrieval_trace` | PureLink retrieval trace 是什么？ | records candidate and final evidence metadata, selected mode | Source basis: PureLink retrieval and citation documentation  Adaptation: concise project-specific facts for deterministi; PureLink supports several retrieval modes. chunkonly performs vector retrieval over indexed chunks. overview collects br | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `def_document_block` | DocumentBlock 是什么？ | DocumentBlock records preserve structure, source spans | DocumentBlock records preserve structure such as headings, text blocks, tables, code blocks, page metadata, and source s | `hybrid_text` | router_mode_mismatch |
| `attr_alice_location` | Alice Chen 在哪里办公？ | 办公地点：Singapore | 办公地点：Shanghai; 合作伙伴：Alice Chen | `chunk_only` | forbidden_evidence_selected |
| `attr_aurora_pro_weight` | Aurora Pro 重量是多少？ | 重量：2.1 kg | 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w; 颜色：灰色  重量：8.5 kg  特点：可扩展  适用场景：团队部署  Aurora Server is a team deployment device. It is much heavier than the portable mod | `chunk_only` | expected_evidence_not_selected, forbidden_evidence_selected, citation_missing |
| `attr_cheshire_cat` | Cheshire Cat 有什么特点？ | grin and its ability to vanish, leaving the smile visible | 角色：产品经理  办公地点：Beijing  负责：知识库工作台和用户研究  隶属：Product Group  Carol Wang defines workspace workflows and collects user feedba; 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w | `chunk_only` | citation_missing |
| `attr_instance_state` | Python instance object 如何保存状态？ | stores per-object state, Instance attributes | Instantiation calls the class object like a function and creates a new instance object. If the class defines init, Pytho; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | expected_evidence_not_selected |
| `attr_deepseek_config` | DeepSeek API 配置位于哪里？ | API paths, environment variables, code-like tokens | FastAPI includes dependency information in OpenAPI when it affects parameters or security. This allows generated API doc; Database sessions are a common dependency. A session dependency can open the database session, yield it to the endpoint, | `hybrid_text` | expected_document_not_retrieved, expected_evidence_not_selected, router_mode_mismatch, citation_missing |
| `attr_block_aware_features` | block_aware 有什么特点？ | uses document block boundaries and source spans, respect headings | 颜色：蓝色  重量：0.9 kg  特点：轻薄  适用场景：差旅  Aurora Air is the lightest model in this catalog. Its blue finish and 0.9 kg weight ma; 颜色：黑色  重量：2.1 kg  特点：高性能  适用场景：本地模型推理  Aurora Pro is the performance-oriented model. It is heavier than the Mini and Air | `hybrid_text` | router_mode_mismatch, citation_missing |
| `reason_python_classes` | Python 为什么使用 class？ | modeling many objects, separate state | After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads; A Python class is a user-defined type that organizes data and behavior together. It acts as a namespace for attributes a | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `reason_fastapi_di` | FastAPI 为什么使用 dependency injection？ | keeps route functions focused, shared concerns stay in small functions | Source basis: FastAPI official documentation, Dependencies tutorial  Adaptation: concise paraphrase for deterministic Pu; FastAPI dependency injection lets an endpoint declare reusable requirements instead of creating every object directly in | `graph_vector_mix` | router_mode_mismatch, citation_missing |
| `reason_postgres_mvcc` | PostgreSQL 为什么使用 MVCC？ | readers and writers can often operate without blocking, preserve consistency | Source basis: PostgreSQL official documentation, MVCC and locking  Adaptation: concise paraphrase for deterministic Pure; Serializable isolation provides the strongest behavior by making concurrent transactions appear as if they executed one  | `hybrid_text` | expected_evidence_not_selected, router_mode_mismatch, citation_missing |
| `reason_aurora_mini_mobile` | Aurora Mini 为什么适合移动办公？ | 特点：便携, 适用场景：移动办公 | 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w; After a class statement runs, the class object supports attribute reference and instantiation. Attribute reference reads | `chunk_only` | citation_missing |
| `reason_reprocess_old_docs` | 为什么旧 PureLink 文档需要重新处理？ | do not automatically receive new citation-unit behavior, reprocess the document and rebuild the vector index | 颜色：黑色  重量：2.1 kg  特点：高性能  适用场景：本地模型推理  Aurora Pro is the performance-oriented model. It is heavier than the Mini and Air; Source basis: FastAPI official documentation, Dependencies tutorial  Adaptation: concise paraphrase for deterministic Pu | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `reason_low_score_refusal` | PureLink 为什么在低分证据时拒绝回答？ | Low-scoring or missing evidence can trigger, no-reliable-evidence response | Source basis: FastAPI official documentation, Dependencies tutorial  Adaptation: concise paraphrase for deterministic Pu; Source basis: Python official documentation, Classes tutorial  Adaptation: concise paraphrase for deterministic PureLink | `chunk_only` | expected_evidence_not_selected, citation_missing |
| `rel_carol_group` | Carol Wang 属于哪个组？ | 隶属：Product Group | Carol Wang defines workspace workflows and collects user feedback. She belongs to the Product Group and translates produ; Daniel Zhou reviews access control, permission boundaries, and security test coverage. His work is separate from Carol's | `graph_vector_mix` | expected_evidence_not_selected |
| `rel_endpoint_dependency` | endpoint 和 dependency 是什么关系？ | endpoint uses `Depends`, pass the result into the path operation | An endpoint uses Depends to ask FastAPI to execute a dependency and pass the result into the path operation function. Th; Authentication can also be expressed as dependencies. A route can depend on a current-user dependency, and that dependen | `hybrid_text` | router_mode_mismatch, citation_missing |
| `rel_class_instance` | class 和 instance 是什么关系？ | class object supports attribute reference and instantiation, creates a new instance object | An instance object stores per-object state. Instance attributes can be assigned after construction or initialized in ini; Class variables live on the class object and are shared unless an instance overrides the name. Instance variables live o | `graph_vector_mix` | expected_evidence_not_selected, citation_missing |
| `rel_mvcc_locks` | MVCC 和显式锁是什么关系？ | MVCC reduces many read-write conflicts, explicit locks still exist | MVCC reduces many read-write conflicts, but explicit locks still exist for cases that require stronger coordination. App; 角色：产品经理  办公地点：Beijing  负责：知识库工作台和用户研究  隶属：Product Group  Carol Wang defines workspace workflows and collects user feedba | `hybrid_text` | router_mode_mismatch, citation_missing |
| `rel_rabbit_alice` | White Rabbit 和 Alice 的情节关系是什么？ | Alice follows him, leads her into the rabbit-hole | 角色：检索工程师  办公地点：Singapore  负责：向量索引、混合检索和 reranker 评测  合作伙伴：Bob Li  Alice Chen focuses on retrieval quality. Her work incl; 角色：平台工程师  办公地点：Shanghai  负责：Docker、监控和部署  合作伙伴：Alice Chen  Bob Li maintains the platform runtime. He owns Docker configu | `graph_vector_mix` | expected_evidence_not_selected, citation_missing |
| `rel_citation_chunk` | citation unit 和 chunk 是什么关系？ | smaller evidence spans derived from chunks | 角色：检索工程师  办公地点：Singapore  负责：向量索引、混合检索和 reranker 评测  合作伙伴：Bob Li  Alice Chen focuses on retrieval quality. Her work incl; Parser routing chooses a parser based on file type and available providers. Text files remain sourcetype=text, while Mar | `graph_vector_mix` | expected_evidence_not_selected, citation_missing |
| `rel_parser_block` | parser 和 DocumentBlock 是什么关系？ | parser produces extracted content that later becomes document blocks | Parser routing chooses a parser based on file type and available providers. Text files remain sourcetype=text, while Mar; DocumentBlock records preserve structure such as headings, text blocks, tables, code blocks, page metadata, and source s | `graph_vector_mix` | citation_missing |
| `tech_retrieval_min_score` | RETRIEVAL_MIN_SCORE 默认值是什么？ | `RETRIEVAL_MIN_SCORE` configures | RETRIEVALMINSCORE configures the minimum retrieval score used by answer generation reliability checks. Low-scoring or mi; Source basis: PureLink retrieval and citation documentation  Adaptation: concise project-specific facts for deterministi | `hybrid_text` | expected_evidence_not_selected, citation_missing |
| `tech_chunk_strategy` | CHUNK_STRATEGY 支持哪些值？ | supports `fixed` and `block_aware` | PureLink supports fixed and blockaware chunk strategies. Fixed chunking creates character-based chunks.; Block-aware chunking uses document block boundaries and source spans so chunks better respect headings, pages, tables, a | `hybrid_text` | expected_evidence_not_selected |
| `tech_docker_down_v` | docker compose down -v 有什么影响？ | `docker compose down -v` removes volumes | docker compose down stops and removes containers while preserving named volumes unless volume deletion is requested. doc; 负责：Docker、监控和部署 | `graph_vector_mix` | expected_evidence_not_selected, router_mode_mismatch |
| `tech_fastapi_depends` | FastAPI 中 Depends 的作用是什么？ | uses `Depends` to ask FastAPI | FastAPI includes dependency information in OpenAPI when it affects parameters or security. This allows generated API doc; An endpoint uses Depends to ask FastAPI to execute a dependency and pass the result into the path operation function. Th | `hybrid_text` | expected_evidence_not_selected, citation_missing |
| `tech_python_init` | __init__ 在什么时候调用？ | Python calls it during instantiation | 角色：产品经理; 办公地点：Beijing | `chunk_only` | expected_evidence_not_selected, router_mode_mismatch |
| `tech_graph_vector_mix` | graph_vector_mix 的用途是什么？ | used for relation-oriented questions, merges them with vector chunks | PureLink supports several retrieval modes. chunkonly performs vector retrieval over indexed chunks. overview collects br; graphvectormix is used for relation-oriented questions. It retrieves lightweight graph candidates and merges them with v | `hybrid_text` | citation_missing |
| `tech_text_file_types` | PureLink 支持哪些文本文件类型？ | Markdown-like text, Markdown, PDF, DOCX | 颜色：黑色; 重量：2. 1 kg | `chunk_only` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `tech_source_locator` | citation source locator 能保存什么信息？ | text ranges, section titles, heading paths, PDF pages | Source basis: Project Gutenberg edition of Alice's Adventures in Wonderland; Source basis: FastAPI official documentation, Dependencies tutorial | `graph_vector_mix` | expected_document_not_retrieved, expected_evidence_not_selected, router_mode_mismatch, citation_missing |
| `overview_python_classes` | 总结 Python classes 文档 | Class Definition, Inheritance | PureLink supports several retrieval modes. chunkonly performs vector retrieval over indexed chunks.; overview collects broader summary context. graphvectormix combines lightweight graph candidates with vector candidates. | `overview` | expected_evidence_not_selected |
| `overview_fastapi_dependencies` | 概括 FastAPI dependencies 文档 | Dependency Injection, OpenAPI Integration | An endpoint uses Depends to ask FastAPI to execute a dependency and pass the result into the path operation function. Th; Dependencies can validate input, compute values, open resources, or enforce preconditions before the endpoint logic runs | `hybrid_text` | expected_evidence_not_selected, router_mode_mismatch |
| `overview_postgres_concurrency` | PostgreSQL 并发控制主要包含什么？ | MVCC, Deadlocks | Source basis: PostgreSQL official documentation, MVCC and locking; Adaptation: concise paraphrase for deterministic PureLink evaluation | `hybrid_text` | router_mode_mismatch |
| `overview_team_members` | 当前语料中的团队成员有哪些？ | Alice Chen, Bob Li, Carol Wang | PureLink supports several retrieval modes. chunkonly performs vector retrieval over indexed chunks.; overview collects broader summary context. graphvectormix combines lightweight graph candidates with vector candidates. | `overview` | expected_document_not_retrieved, expected_evidence_not_selected, citation_missing |
| `no_answer_profit` | Acme 去年利润是多少？ | - | A dependency can depend on another dependency. FastAPI resolves this tree and reuses results where appropriate during on; Nested dependencies make it possible to build layered behavior, such as authentication that relies on token parsing and  | `chunk_only` | unexpected_answerable |
| `no_answer_ceo` | Acme 的 CEO 是谁？ | - | 角色：检索工程师  办公地点：Singapore  负责：向量索引、混合检索和 reranker 评测  合作伙伴：Bob Li  Alice Chen focuses on retrieval quality. Her work incl; 角色：平台工程师  办公地点：Shanghai  负责：Docker、监控和部署  合作伙伴：Alice Chen  Bob Li maintains the platform runtime. He owns Docker configu | `hybrid_text` | router_mode_mismatch, unexpected_answerable |
| `no_answer_ipo` | Acme 什么时候上市？ | - | A dependency can depend on another dependency. FastAPI resolves this tree and reuses results where appropriate during on; Nested dependencies make it possible to build layered behavior, such as authentication that relies on token parsing and  | `chunk_only` | unexpected_answerable |
| `no_answer_processor` | Aurora Mini 的处理器型号是什么？ | - | 颜色：灰色  重量：8.5 kg  特点：可扩展  适用场景：团队部署  Aurora Server is a team deployment device. It is much heavier than the portable mod; 颜色：银色  重量：1.2 kg  特点：便携  适用场景：移动办公  Aurora Mini is the compact member of the Aurora catalog. It is designed for people w | `chunk_only` | forbidden_evidence_selected, unexpected_answerable |
| `no_answer_alice_birthday` | Alice Chen 的生日是什么？ | - | The Cheshire Cat is known for its grin and its ability to vanish. It can disappear gradually while leaving the smile vis; 角色：平台工程师  办公地点：Shanghai  负责：Docker、监控和部署  合作伙伴：Alice Chen  Bob Li maintains the platform runtime. He owns Docker configu | `chunk_only` | unexpected_answerable |

## 8. Known Limitations

- This baseline is deterministic and does not use LLM-as-judge.
- Evidence precision is approximated with expected/forbidden phrases and expected document names.
- Evidence-gate answerability means final evidence is non-empty and at least one evidence score reaches RETRIEVAL_MIN_SCORE; it mirrors the production answer gate but does not judge semantic entailment.
- No-answer failures expose limitations of the production evidence gate, not full QA accuracy.
- In-process retrieval latency is only useful for comparison on the same local environment.
- A failed case records retrieval or routing behavior; it is not hidden or rewritten by the runner.
