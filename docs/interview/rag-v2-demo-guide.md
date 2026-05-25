# PureLink RAG v2 Demo Guide

## 1. 启动项目

```bash
make up
```

本地 API 默认在：

```text
http://localhost:8000
```

## 2. 准备测试知识库

创建一个个人知识库或团队知识库，上传这些项目文档：

- `README.md`
- `docs/architecture/rag-v2-architecture.md`
- `docs/retrieval-and-citations.md`
- `docs/roadmap/M2-model-provider-standardization.md`
- `docs/roadmap/M3-optional-reranker-integration.md`
- `docs/roadmap/M4-index-version-and-rebuild-readiness.md`
- `docs/roadmap/M5-retrieval-trace.md`
- `docs/roadmap/M6-document-block-schema-parser-routing.md`
- `docs/roadmap/M7-lightweight-graphrag-and-rag-v2-closure.md`
- `docs/roadmap/M8-lightweight-rag-evaluation.md`

如果本地有 M1 roadmap，也一起上传；否则可以用 `docs/architecture/rag-v2-architecture.md` 覆盖 M1 讲解。

## 3. 等待索引完成

确认：

- document status 变为 `indexed`
- `document_indexes.vector` 为 `indexed`
- `document_indexes.graph` 为 `indexed`，或失败但不影响普通 vector RAG

Graph index 失败不应该阻塞普通问答，这是 M7 的设计边界。

## 4. 手动问答演示问题

推荐问题：

- PureLink 的文档处理流程是什么？
- Retrieval Layer 解决了什么问题？
- reranker 在检索链路中起什么作用？
- document_indexes 为什么重要？
- retrieval trace 能定位哪些问题？
- DocumentBlock 在解析中有什么作用？
- GraphRAG 在 PureLink 中怎么参与检索？
- RAG eval harness 评估哪些指标？

演示时重点看：

- answer 是否非空
- citation 是否指向真实文档
- source locator / document name 是否清楚
- trace id 是否存在

## 5. Eval 演示

复制模板 case：

```bash
cp tests/eval/purelink_rag_interview_cases.template.jsonl tests/eval/purelink_rag_interview_cases.local.jsonl
```

编辑 local JSONL：

- 替换 `knowledge_base_id`
- 替换 `user_id`
- 按本地上传后的真实文件名调整 `expected_doc_names`

运行：

```bash
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

指定输出：

```bash
make eval-rag \
  EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl \
  EVAL_OUTPUT=tests/eval/reports/rag-v2-baseline.json
```

## 6. 对比检索模式

对同一组 case 对比：

```bash
.venv/bin/python scripts/eval/run_rag_eval.py \
  --cases tests/eval/purelink_rag_interview_cases.local.jsonl \
  --mode chunk_only \
  --output tests/eval/reports/chunk-only.json

.venv/bin/python scripts/eval/run_rag_eval.py \
  --cases tests/eval/purelink_rag_interview_cases.local.jsonl \
  --mode graph_vector_mix \
  --output tests/eval/reports/graph-vector-mix.json
```

观察：

- retrieval hit
- citation hit
- keyword coverage
- top-1/top-3 doc hit
- trace availability
- initial candidate count

## 7. 演示重点

- citations 由后端基于 evidence 生成，不让 LLM 编来源。
- trace id 证明检索过程可追踪。
- `graph_vector_mix` 是增强模式，不替代默认 vector RAG。
- eval report 可以展示 retrieval/citation baseline。
- 项目明确承认限制：不是完整 LightRAG、不是完整多模态、还没有 Agent runtime。

## 8. 关闭项目

```bash
make down
```
