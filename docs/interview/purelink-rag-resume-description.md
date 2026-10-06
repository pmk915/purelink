# PureLink 简历与面试描述

## 项目定位

PureLink：本地优先、可自部署的工程化 RAG 知识工作台，聚焦结构化处理、
检索与证据选择的分离、回答支持、引用溯源和可复现评估。功能已冻结。

## 简历 Bullet

- 基于 FastAPI、PostgreSQL、Redis、Next.js 与 Python worker 实现个人/团队
  知识库、上传审核、异步处理、问答与会话，保持 ownership/membership 边界。
- 建立 TXT/Markdown/DOCX/PDF → DocumentBlock → chunk → citation unit 链路，
  保留来源范围和 PDF 物理页码；候选检索、最终证据、支持门禁和引用各自可追踪。
- 用独立 24 例格式基准定位“文档 Recall@5=100%，证据精度只有 29.6%”的瓶颈；
  受控证据选择与匹配修正将精度提升到 72.5%、证据召回从 90% 提升到 100%，
  文档 MRR=.925、原 50 例回归保持；拒绝召回降至 80% 的 coverage-only 方案。
- 使用官方 MTEB qrels 对六个 NanoBEIR 任务的 300 个查询做部分外部验证；
  固定英文 BGE/FastEmbed/CPU，PureLink Dense nDCG@10=.6226，参考=.6222。
  现有 Hybrid=.5569，六任务 nDCG 均下降，保留负面结果，不在公开任务上调参。

## 面试展开

使用 [Project Storyline](project-storyline.md) 的五分钟路径：假设 → 测量 →
发现 → 工程决策。代码入口见 [Code Tour](code-tour.md)，演示见
[Demo Guide](purelink-demo-guide.md)。详细定义与分母见
[Evaluation](../rag/rag-evaluation.md) 和 [Ablation](../rag/evidence-selection-ablation.md)。

Reranking 和轻量图候选是可选能力，不是本轮核心改善结果。图数据在 PostgreSQL
中保存一跳关系及来源；AUTO 是规则式路由。公共验证不涉及 QA/PDF/证据选择，
没有完整 NanoBEIR 或官方 MTEB 排名。内部短语指标不代表语义答案正确率。

## 限制与当前决策

七个格式案例仍含 forbidden evidence；复杂 PDF 布局、表格和 OCR 完整性有限。
没有企业安全审计或生产规模压力测试，Go worker 是实验性实现。M4 provider
修正应保留，旧 FastEmbed 索引必须完整重建。详见 [Limitations](limitations.md)。
当前决定是作品集收口和功能冻结，不启动 M5 或扩展新的 RAG 模块。
