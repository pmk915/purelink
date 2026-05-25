# PureLink RAG 简历描述草稿

## 简历项目描述：短版

PureLink：面向团队知识库的工程化 Agent-ready RAG 系统

基于 FastAPI、PostgreSQL、Redis、Next.js 构建团队知识库平台，支持个人/团队知识库、文档上传、异步解析、权限审核、引用溯源和 RAG 问答。围绕 RAG 内核完成工程化升级：设计统一 Retrieval Layer 和模型 Provider Layer，引入 optional reranker、document index metadata、retrieval trace、DocumentBlock parser routing 和轻量 GraphRAG；支持 graph-vector mixed retrieval，并通过 JSONL eval harness 评估 retrieval hit、citation hit、keyword coverage 和 top-k doc hit。

## 简历项目描述：Bullet 版

- 基于 FastAPI、PostgreSQL、Redis、Next.js 构建团队知识库平台，支持个人/团队知识库、文档上传、异步解析、权限审核、引用溯源和 RAG 问答；
- 设计统一 Retrieval Layer，将证据检索与答案生成解耦，支持 chunk-only、overview、graph-vector-mix 等检索模式；
- 抽象 Embedding/Reranker/LLM Provider，支持轻量本地 embedding 与可选 reranker，避免模型实现与业务逻辑耦合；
- 引入 `document_indexes` 记录索引使用的 provider、model 和向量维度，避免 embedding 模型切换后新旧向量混用；
- 实现 retrieval trace，记录候选 evidence、向量分数、rerank 分数、过滤原因和最终引用证据，用于定位 RAG 质量问题；
- 参考 LightRAG 思路实现轻量 GraphRAG，抽取实体/关系并绑定 citation source，将 graph candidates 与 vector candidates 合并后统一重排；
- 构建 JSONL RAG eval harness，评估 retrieval hit、citation hit、keyword coverage 和 top-1/top-3 doc hit。

## 面试追问准备

### 为什么不直接用 LightRAG？

PureLink 有自己的团队知识库、权限、审核、citation、文档状态和异步处理系统。直接接入完整 LightRAG 容易造成状态重复和权限绕行，也会让 product workflow 和 retrieval workflow 脱节。

PureLink 的做法是借鉴 graph + vector mixed retrieval 思路，但保留自己的 evidence、citation、trace、index metadata 和 permission 模型。

### GraphRAG 在项目里怎么参与检索？

文档 indexed 后，系统从 chunk/citation unit 中抽取实体、关系和 mention，并把关系绑定到 source document、chunk、citation unit。

查询时：

```text
query -> match entities -> graph candidates -> vector candidates -> merge -> optional rerank -> final evidences
```

最终答案仍然基于 citation-ready evidence，不让图谱结果脱离原文来源。

### Reranker 和 embedding 检索有什么区别？

embedding retrieval 是第一阶段召回，适合从大量 chunk 中快速找候选。

reranker 是第二阶段排序，对 query-document pair 做更精细相关性判断。它通常更慢，但更准确，所以放在 top-N recall 之后，只处理候选集。

### 为什么需要 document_indexes？

embedding vectors 依赖 provider、model 和 dimension。不同 embedding model 的向量空间不能安全混用。

`document_indexes` 记录每个文档的 vector index 是用哪个 provider/model/dim 生成的。当配置变化时，系统可以检测 stale 或 incompatible index，避免静默拿旧向量做新查询。

### retrieval trace 解决什么问题？

trace 把一次检索拆成可检查的记录：初始候选、vector score、rerank score、graph score、过滤原因、最终 evidence 和 trace id。

当回答质量不好时，可以判断问题来自解析、chunking、embedding recall、rerank、index 兼容、citation selection 还是 prompt generation。

### 这个项目还有哪些限制？

GraphRAG 当前是轻量规则版，不是完整 LightRAG；没有外部图数据库、复杂多跳推理或 graph visualization。多模态能力默认关闭，也没有完整 Agent runtime。
