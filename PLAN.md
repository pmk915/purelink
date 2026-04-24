# PureLink 续聊交接摘要（给新对话 / 新 Codex）

## 0. 仓库与当前形态

- 仓库路径：`/home/pmk/projects/purelink`
- 当前项目已经不是纯后端仓库，而是：
  - FastAPI 后端
  - PostgreSQL 数据库
  - Go worker
  - Next.js 前端
- 当前目标不是重新起盘，而是在现有可运行原型上继续收口、稳态化和产品化

## 1. 当前已经完成的核心能力

- 认证闭环已完成：注册、登录、JWT、当前用户
- 个人知识库 CRUD 已完成
- 团队域能力已完成基础闭环：
  - Team / TeamMember / TeamInvite
  - 团队创建、邀请码、入队、成员查看
- 团队知识库 CRUD 已完成
- 文档上传与审核基础闭环已完成：
  - 个人知识库文档上传
  - 团队知识库文档上传
  - 团队待审核列表、通过、拒绝
- 文档处理链最小闭环已完成：
  - parse
  - chunk
  - embed / index
- 基础检索、最小问答、conversation / message 持久化已完成
- Bash E2E、smoke、CI 基础能力已完成

## 2. 最近一轮关键调整

最近一轮最重要的调整，不是新增业务功能，而是把“前端联调”和“文档处理闭环”做得更可用。

### 2.1 前端“开始处理”改为默认走同步闭环

- 前端现在默认直接调用同步处理接口：
  - `parse`
  - `chunk`
  - `embed`
- 这样做的原因是：此前 UI 走 `document_tasks` 异步任务链时，如果 Go worker 没启动，文档会长时间停留在“处理中”
- 现在的默认策略是：
  - 前端手动联调：默认走同步闭环，不依赖 worker
  - E2E / smoke / worker 验证：继续保留 `document_tasks + Go worker` 方案

### 2.2 后端补了更明确的处理日志和失败回写

- 在以下服务中增加了步骤级日志：
  - `app/services/document_parser.py`
  - `app/services/document_chunker.py`
  - `app/services/document_embedding.py`
- 现在会打印：
  - 文档开始处理
  - 源文件路径
  - 中间产物路径
  - chunk / embedding 数量
  - 异常信息
- 同时补了失败状态回写：
  - chunk 失败时会把 `processing_status` 改为 `failed`
  - 不再让文档长期卡在“处理中”

### 2.3 针对失败回写补了回归测试

- 已在 `tests/test_documents.py` 中补充最小回归测试
- 重点覆盖：非法 chunk 输入时，文档状态会正确回写为 `failed`

## 3. 最近更新过的文档

以下文档已经在最近一轮被整理过，后续续开发时应优先以这些文件为准：

- `README.md`
  - 现在更偏公开展示和项目介绍
- `DEVELOPMENT_LOG.md`
  - 记录阶段推进、联调说明、近期收口内容
- `PLAN.md`
  - 当前阶段计划与后续路线
- `test.md`
  - 前后端联调、全流程验证、手动测试说明
- `DEV_COMMANDS.md`
  - 日常开发高频命令、数据库查看、Git/GitHub 操作
- `frontend/README.md`
  - 前端局部说明，包含处理链路的当前行为

## 4. 当前运行与验证口径

### 4.1 手动前后端联调

当前推荐的最短联调路径是：

1. 启动 PostgreSQL
2. 启动 FastAPI
3. 启动 Next.js 前端
4. 在前端完成：
   - 注册 / 登录
   - 创建知识库
   - 上传 `.txt` / `.md`
   - 点击“开始处理”
   - 检索
   - 问答

这里默认不要求必须先启动 Go worker，因为前端手动处理现在默认走同步闭环。

### 4.2 全流程自动化验证

以下场景仍然依赖 worker：

- `scripts/e2e/*.sh`
- `scripts/e2e/run_all.sh`
- `make smoke`
- `make e2e`
- Docker compose 下的完整处理任务链验证

因此：

- 手动 UI 联调：worker 不是前置依赖
- 任务链 / E2E / smoke：worker 是前置依赖

## 5. 数据库与本地开发环境现状

- 当前数据库跑在本机 Docker 容器里，不是远程数据库
- 默认是 PostgreSQL
- 数据可以通过以下方式查看：
  - `docker compose exec db psql -U purelink -d purelink`
  - VS Code + SQLTools + PostgreSQL driver
- 数据卷由 Docker volume 持久化，通常不会因为容器重启而消失
- 但如果执行 `docker compose down -v`，数据库数据会被清空

## 6. Git 与仓库状态的注意事项

- 当前仓库已经补了公开仓库所需的基础文件，例如：
  - `LICENSE`
  - `CONTRIBUTING.md`
- `.gitignore` 已覆盖常见本地与中间产物，例如：
  - `.env`
  - `.venv`
  - `data/uploads`
  - `data/parsed`
  - `data/chunks`
  - `data/vector_store`
  - `logs`
  - `frontend/node_modules`
  - `frontend/.next`
- 当前不要机械地直接执行 `git add .`
- 更稳妥的方式是先看 `git status --short`，再按目标分批提交

## 7. 继续开发时应优先遵守的判断

- 前端已经不是当前唯一短板，后端处理稳定性、状态机和可观测性更重要
- 不要轻易把 UI 再改回完全依赖异步 worker 的模式，除非任务调度、状态回写和失败诊断已经补齐
- 后续新增能力时，优先保持：
  - 个人知识库逻辑继续可用
  - 团队知识库权限边界不被破坏
  - 文档处理失败必须可诊断、可回写
  - 文档处理中间产物路径保持一致，可追踪

---

# PureLink 当前阶段项目计划书（给 Codex）

## 已完成部分概括

在进入当前阶段目标之前，需要先明确：PureLink 并不是从零开始，而是已经完成了一批可运行、可联调、可验证的基础建设。当前阶段要解决的是“把原型做稳、把链路做透”，不是重新起盘。

### 1. 已完成的产品与业务基础

- 已完成用户注册、登录、JWT 鉴权和当前用户查询
- 已完成个人知识库 CRUD，以及按所有权隔离的数据访问
- 已完成团队域模型、团队创建、邀请码、入队、成员管理
- 已完成团队知识库 CRUD 和基础权限边界
- 已完成团队文档审核流，审核通过后才进入检索链路

### 2. 已完成的文档处理与问答闭环

- 已支持 `.txt / .md / .pdf / .docx` 文档上传与统一处理
- 已具备统一 `/process` 标准链路：
  - 保存原始文件
  - 提取文本
  - 生成数据库 `DocumentChunk`
  - 状态进入 `uploaded -> processing -> ready / failed`
- 已将 retrieval / ask 主路径收口到 `DocumentChunk`
- `ready` 文档已可直接进入最小检索与问答，`indexed` 兼容链路继续保留
- 已具备最小 `parse -> chunk -> embed / index` 兼容链路
- 已具备基础检索能力和最小问答链路
- 检索层已兼容：
  - `ready`
  - `indexed`
- 已支持问答会话与消息持久化
- 已具备最小 citations 返回与元数据保存能力
- 已引入 `ProcessingJob` 基线：
  - `/process` 会创建任务并记录步骤
  - 支持 `retry-process / reprocess`
  - 支持按文档列出 processing jobs 和按 job 查询详情
- 已打通前端“开始处理”触发统一 `/process` 闭环，以及基于 `document_tasks` 的兼容任务链路
- 已引入 Go worker，承担 `parse / chunk / embed / index` 等任务执行能力
- 已在 Docker + PostgreSQL 真库里完成 M13 live smoke 验证
- 已修复 PostgreSQL 真库上 `documents.processing_status` 长度不足导致 `/process` 报 `500` 的问题，对应迁移版本 `20260423_0008`

### 3. 已完成的前端与交付基础

- 已有可运行的 Next.js 前端工作台
- 前端方向已从“开发演示页”调整为“真实用户工作台”
- 已支持从前端完成注册、知识库创建、上传、处理、检索和基础问答联调
- 已具备 FastAPI + PostgreSQL + Alembic + Docker Compose 本地运行环境
- 已完成 Docker 环境下真实数据库迁移与 live API 验证
- 后端代码更新后，Docker 联调应使用 `docker compose up -d --build api` 使容器吃到最新镜像
- 已具备 Bash E2E、smoke 验证和最小 CI 工作流

### 4. 当前阶段与前序成果的关系

前面这些成果说明，PureLink 已经具备“最小可运行原型”和“基础文本链路闭环”的雏形；但同时也说明当前短板已经非常明确：

- 前端不再是核心瓶颈，后端文件处理稳定性才是当前主问题
- 现有统一文本链路、最小引用问答和 `ProcessingJob` 基线已经落地，但真正的异步解耦、独立 worker 和队列化还未完成
- 问答已经具备雏形，但来源引用、状态机、失败回写和多格式扩展仍不完整

因此，当前阶段的工作重点不是继续平铺更多页面或功能点，而是把已完成能力工程化、标准化，并为后续多模态扩展打基础。

---

## 0. 项目背景与当前状态

PureLink 当前已经具备以下基础能力：

- 前端基础工作台已可用
- 用户可以上传 `.txt / .md / .pdf / .docx` 文件
- 基础检索功能已经可用
- 前端 UI 已从“展示开发成果”调整为“真实用户工作台”方向
- 当前主要问题已经从前端展示层，转移到后端文件处理与知识链路完善层

当前阶段的核心目标不是继续堆前端页面，而是：

**把 PureLink 从“能上传、能检索”的原型，推进为“能稳定处理文件、能支持引用问答、能扩展到多模态”的知识工作台。**

---

## 1. 当前阶段的核心问题总览

### 1.1 前端层面

前端目前不再是主要矛盾，但需要继续保持以下原则：

- 页面文案必须面向真实用户，而不是面向开发者
- 不再暴露 MVP / 开发中 / parse / chunk / embed 等内部信息
- 首页定位为“工作台”，不是“演示页”
- 文档状态提示必须用户可理解，例如：
  - 已上传
  - 处理中
  - 待审核
  - 可检索
  - 处理失败

### 1.2 后端层面

当前后端是主要问题来源，尤其集中在文件处理链路：

- 文档上传后，点击“开始处理”会长时间停留在处理中
- 后端文件处理流水线没有真正闭环
- 当前尚未建立标准化、可重试、可扩展的文件处理架构
- 检索虽然已有基础能力，但问答与引用链路尚未完整
- 文档处理的状态机、任务系统、错误回写机制仍需完善

### 1.3 产品层面

目前需要从“文本文件原型”升级到“团队知识资产系统”的产品设计：

- 上传后不能只是保存文件，还要转化为知识资产
- 后续要支持多模态输入，不仅是 `txt`，还包括：
  - `docx`
  - `pdf`
  - 图片
  - 扫描件
  - 音频
  - 视频
- 问答结果不能只输出答案，必须逐步支持来源引用

---

## 2. 当前阶段的产品目标

### 2.1 PureLink 的产品定位

PureLink 应定位为：

**面向团队的知识工作台 / 多模态知识资产平台**

而不是单纯的聊天工具或文件上传页面。

### 2.2 当前阶段最重要的产品目标

本阶段优先完成以下产品闭环：

1. 用户上传文本文档
2. 系统保存原始文件
3. 后端自动或触发式处理文档
4. 文档进入可检索状态
5. 用户基于知识库进行检索与问答
6. 问答结果带有来源依据（逐步实现）

### 2.3 当前阶段不应盲目追求的内容

当前阶段不建议直接深做：

- 复杂 Agent 工作流
- 完整视频理解
- 高级视觉问答
- 本地超大模型部署
- 过度优化存储压缩

本阶段的重点应该是：

**先把文本链路做透，再为多模态和高并发打基础。**

---

## 3. 当前阶段的关键技术问题整理

### 3.1 原始文件保存策略

#### 当前要解决的问题

上传后的原始文件应该怎么保存，才能支持后续处理、重试、引用和扩展。

#### 当前建议方案

- 原始文件必须保留
- 原始文件不保存在用户本地
- 原始文件不直接存入数据库大字段
- 原始文件先保存在服务端文件存储中
- 当前阶段可以先使用：
  - Docker 挂载目录
  - 本地磁盘目录
- 后续可升级到：
  - MinIO
  - S3 兼容对象存储
  - OSS / COS 等云对象存储

#### 数据库存储内容

数据库只保存：

- 文件元数据
- 存储路径或 `storage_key`
- `hash`
- `mime_type`
- 大小
- 状态
- 处理结果索引

#### 关于压缩

当前阶段不优先做原始文件压缩，优先保证：

- 可追溯
- 可重处理
- 可引用
- 可扩展

后续再考虑：

- 冷热分层
- 归档压缩
- 低频文件迁移

### 3.2 文件处理思想与架构思想

当前方案使用的核心思想包括：

#### 1）分层处理思想

文件进入系统后分三层处理：

- 原始文件层
- 结构化内容层
- 检索表示层

#### 2）统一中间表示思想

不论输入是：

- `txt`
- `pdf`
- `docx`
- 图片
- 音频
- 视频

最终都要转成统一 `block / chunk` 表示，便于后续：

- 检索
- 问答
- 引用
- 多模态扩展

#### 3）Grounded QA / Citation-aware QA 思想

回答必须尽量基于已检索到的来源内容，而不是让模型自由发挥。

#### 4）可重处理思想

文档处理不是一次性动作，而是一条可重跑的流水线。

### 3.3 当前方案是否属于 RAG

是，当前方案本质上就是标准 RAG 的工程化实现：

- 文档接入
- 内容提取
- `chunk` 切分
- `embedding`
- 检索召回
- 将召回结果作为上下文传给大模型
- 生成答案

后续 PureLink 应逐步升级为：

- 标准文本 RAG
- Citation-aware RAG
- Hybrid Retrieval
- 多模态 RAG（中后期）

### 3.4 当前技术栈兼容性

当前方案需要兼容现有技术栈：

- FastAPI
- PostgreSQL
- Redis
- Docker
- Next.js
- 未来可能加入 Go 组件

#### 兼容性判断

当前方案与现有技术栈兼容，且比较适合：

- FastAPI：负责 API、权限、元数据、问答编排、任务下发
- PostgreSQL：负责文档元数据、`chunk`、`citation`、`processing_job`、`conversation` 等
- Redis：负责任务队列、缓存、状态辅助
- Docker：负责本地环境和后续服务拆分
- Go：后续适合引入到高并发文件服务、任务调度、通知服务等模块

### 3.5 高并发与大量数据问题

虽然当前还是本地开发阶段，但要提前为后续扩展预留设计。

#### 可能遇到的问题

- 多用户同时上传文件
- 大量文档集中处理
- 向量化耗时
- 检索数据量增大
- 问答并发增大
- 音频或视频处理耗时很长

#### 当前建议策略

##### 阶段 1：中小规模

- 主服务 + Python worker 即可
- 上传与处理解耦
- 文档处理异步化

##### 阶段 2：任务系统化

- 引入 `ProcessingJob`
- Worker 池
- Redis 队列
- 重试机制
- 幂等设计

##### 阶段 3：服务拆分

后续可拆成：

- API 服务
- 文档处理服务
- 检索服务
- 问答编排服务

##### 阶段 4：Go 引入场景

Go 后续适合用于：

- 高并发上传服务
- 大文件传输
- 任务调度器
- 状态通知服务
- 文件扫描同步

### 3.6 检索问答方案可行性

当前想法是：

**文本处理完成后，通过 API 调用大模型，在对话端提供检索问答功能。**

#### 结论

该方案完全可行，而且是当前阶段最推荐的方法。

#### 推荐链路

用户提问  
→ query 预处理  
→ 检索 `chunk`  
→ 可选 rerank  
→ 组装上下文  
→ 调用大模型 API  
→ 返回答案 + citation

#### 当前阶段不建议的替代方案

当前不建议一开始就上：

- 复杂 agent orchestration
- 多轮 autonomous workflow
- 本地大模型完整推理链

当前最优先的是：

**高质量 RAG + 来源引用**

---

## 4. 当前阶段必须修复或完善的问题清单

### P0（最高优先级，必须尽快完成）

1. 文档“开始处理”后长期卡在 `processing`
2. 后端处理链路缺少完整闭环
3. 异常发生后没有正确回写 `failed` 状态
4. 处理完成后没有可靠地进入 `ready` 状态
5. 缺少标准化 `ProcessingJob` 或等价任务跟踪机制
6. 缺少后端处理分步骤日志和错误追踪

### P1（应尽快推进）

7. 原始文件保存策略标准化
8. 文档状态机标准化
9. 文本抽取、`chunk`、`embedding` 流程标准化
10. 引用数据结构设计
11. 检索问答 API 设计
12. 前后端状态同步完善

### P2（中期推进）

13. `pdf` / `docx` 支持完善
14. 图片 OCR 接入
15. 扫描件处理策略
16. 音频转写策略
17. 视频转写与时间戳引用策略
18. 高并发任务架构预留

---

## 5. 文件处理模块设计目标

### 5.1 文件处理模块要达成的能力

当用户上传文件以后，系统应能：

1. 保存原始文件
2. 记录文档元数据
3. 根据文件类型选择处理器
4. 提取结构化内容
5. 切分 `chunk`
6. 生成 `embedding`
7. 写入检索索引
8. 更新状态
9. 支持重试或重处理
10. 为后续引用与问答提供依据

### 5.2 处理后的目标结果

最终，文档不是简单“存进系统”，而是变成：

**可管理、可检索、可引用、可问答的知识资产**

---

## 6. 标准文件处理流水线（需要 Codex 逐步实现）

### Step 1：上传与校验

要求：

- 验证用户身份
- 验证知识库权限
- 验证文件类型
- 验证大小限制
- 计算 `hash`
- 处理重复上传策略

### Step 2：保存原始文件

要求：

- 原始文件落服务端存储
- 记录 `storage_key / path`
- 不直接把原始二进制写入数据库
- 保留 `original_filename`、`mime_type`、`size`、`sha256`

### Step 3：创建 Document 元数据

初始状态建议：

- `uploaded`

记录内容包括：

- `knowledge_base_id`
- `uploader_id`
- `file_type`
- `storage_path`
- `hash`
- `upload_time`
- `processing_version`

### Step 4：创建 ProcessingJob

要求：

- 上传成功后投递处理任务
- 上传接口与处理任务解耦
- 后续可以支持重试、重跑、审核流

### Step 5：内容提取

按文件类型分别走 extractor：

#### 第一阶段必须支持

- `txt`
- `md`
- `docx`
- `pdf`

#### 第二阶段支持

- 图片（OCR）
- 扫描版 `pdf`

#### 第三阶段支持

- 音频（ASR）
- 视频（优先走音频转写）

### Step 6：统一结构化表示

建议抽象出 `block`：

- `block_id`
- `document_id`
- `block_type`
- `text_content`
- `order_index`
- `page_number`
- `section_title`
- `start_time / end_time`
- `bbox / region`

### Step 7：chunk 切分

第一阶段先做：

- 固定长度
- overlap

后续增强：

- 按段落
- 按标题
- 按页
- 按时间段
- 按语义边界

### Step 8：embedding 与索引

要求：

- 将 `chunk` 向量化
- 保存 `chunk metadata`
- 支持按 `knowledge_base / document` 过滤
- 为检索和问答提供上下文来源

### Step 9：更新状态

状态建议至少包含：

- `uploaded`
- `queued`
- `processing`
- `pending_review`
- `ready`
- `failed`
- `archived`
- `reprocessing`（后续）

> 说明：若现有实现仍使用 `completed`、`indexed` 等终态，应在本阶段逐步统一为面向产品与前端可解释的状态语义。

### Step 10：支持失败回写与重试

要求：

- 任一步失败必须进入 `failed`
- 必须记录 `error_message`
- 支持 `retry / reprocess`

---

## 7. 当前阶段的数据模型建议（重点保留）

当前阶段建议优先补齐或完善以下模型：

### 7.1 Document

存文档主记录：

- `id`
- `knowledge_base_id`
- `owner_id`
- `team_id`（可选）
- `title`
- `original_filename`
- `mime_type`
- `file_size`
- `storage_key`
- `sha256`
- `status`
- `error_message`
- `uploaded_at`
- `processed_at`
- `processing_version`

### 7.2 ProcessingJob

存处理任务：

- `id`
- `document_id`
- `job_type`
- `status`
- `retry_count`
- `error_message`
- `started_at`
- `finished_at`
- `worker_info`

### 7.3 DocumentBlock

存结构化内容块：

- `id`
- `document_id`
- `block_type`
- `text_content`
- `page_number`
- `section_title`
- `order_index`
- `start_time / end_time`
- `region metadata`

### 7.4 DocumentChunk

存检索块：

- `id`
- `document_id`
- `block_id`（可选）
- `chunk_text`
- `chunk_index`
- `token_count`
- `metadata_json`

### 7.5 EmbeddingRecord（可并入 chunk，视实现决定）

- `chunk_id`
- `vector`
- `embedding_model`
- `embedding_version`

### 7.6 Citation

当前阶段即使不完全实现，也应先设计结构：

- `id`
- `conversation_id / answer_id`
- `document_id`
- `chunk_id`
- `snippet`
- `page_number / timestamp`
- `source_locator`

---

## 8. 当前阶段的问答能力建设目标

### 8.1 当前阶段推荐方案

采用：

**检索 + API 大模型生成 + 引用返回**

### 8.2 最小可行问答链路

1. 用户提问
2. 检索相关 `chunk`
3. 组装上下文
4. 调用大模型 API
5. 返回 `answer`

### 8.3 下一步增强

在回答结果中加入：

- 文件名
- `chunk snippet`
- 页码或时间戳
- `document_id`
- 下载或预览入口

### 8.4 当前阶段不要求立即做的复杂功能

- 多跳复杂 agent 检索
- 全自主任务流
- 高级工具调用编排

---

## 9. 项目阶段规划（当前最重要）

### Phase 0：修复当前后端处理闭环（最高优先级）

#### 目标

解决文档一直 `processing` 的问题，让 `txt` 文档完整走通。

#### 必须完成

- 定位“开始处理”真实后端接口
- 确认是否只是改状态，没有真处理
- 增加分步骤日志
- 增加失败回写
- 增加 `ready` 状态回写
- 确认前端刷新可获取正确状态

#### 完成标准

- 上传 `txt` 成功
- 点击开始处理后真正完成处理
- 文档进入 `ready`
- 失败时进入 `failed`
- 前端状态可见

### Phase 1：做透文本文件处理链路

#### 支持格式

- `txt`
- `md`
- `pdf`
- `docx`

#### 完成目标

- 原始文件保存
- 内容提取
- `block / chunk` 生成
- `embedding`
- 检索
- 状态机
- `ProcessingJob`
- 错误处理
- 基础问答

#### 完成标准

至少一类文本知识库可以完整走通：

上传 → 处理 → 检索 → 回答

### Phase 2：实现引用能力雏形

#### 目标

让问答具备可验证性。

#### 完成内容

- `Citation` 数据结构
- 回答时返回来源 `chunk`
- 返回文件名和片段
- `pdf` 至少支持页码引用（如果已有页级处理）

#### 完成标准

用户提问后，不仅有答案，还有来源依据。

### Phase 3：把处理链路工程化

#### 目标

让文档处理从“函数调用”升级为“标准流水线”。

#### 完成内容

- `Extractor` 抽象
- `Chunker` 抽象
- `EmbeddingProvider` 抽象
- `ProcessingJob` 标准化
- Worker / Queue 接入
- `Retry / Reprocess` 机制
- 结构化日志

### Phase 4：扩展图片与扫描件

#### 目标

支持 OCR 场景。

#### 完成内容

- `png / jpg / jpeg` 上传
- OCR 文本提取
- 扫描版 `pdf` OCR
- OCR block 定位
- 引用回源

### Phase 5：扩展音频与视频

#### 目标

逐步支持更多多模态内容。

#### 优先顺序

先音频，后视频。

#### 音频阶段

- 音频上传
- ASR 转写
- 时间段切分
- 检索与时间戳引用

#### 视频阶段

- 视频提取音轨
- 转写
- 基于转写检索
- 时间戳引用

### Phase 6：为高并发与开源化做准备

#### 完成内容

- MinIO / S3 对象存储抽象
- 独立 worker 服务
- Redis 队列
- Go 组件预留接口
- 配置化模型 provider
- README / Roadmap 完善

---

## 10. 当前阶段 Codex 具体工作要求

### 10.1 优先处理后端 processing 卡死问题

请优先排查和修复：

- “开始处理”对应接口
- 状态回写逻辑
- 文件读取逻辑
- 任务执行逻辑
- `failed / ready` 状态更新逻辑

### 10.2 逐步建立文件处理标准化架构

不要继续堆零散逻辑，请以以下方向重构：

- 文档状态机
- `ProcessingJob`
- `Extractor` 抽象
- `Block / Chunk` 数据层
- 统一处理入口

### 10.3 保证当前方案与技术栈兼容

实现时必须考虑：

- FastAPI 作为主服务
- PostgreSQL 作为元数据中心
- Redis 作为队列辅助
- Docker 下可运行
- 后续可迁移到对象存储
- 后续可支持 Go 组件协作

### 10.4 问答功能建设要求

短期内采用：

- API 调大模型
- 标准 RAG
- 后续支持 citation

不要在当前阶段优先引入：

- 复杂 agent
- 本地超大模型链路
- 过度复杂的推理编排

---

## 11. 当前阶段的设计原则（必须保留）

请确保后续实现始终遵循以下原则：

### 原则 1：原始文件不丢

原始文件必须可追溯、可预览、可重处理。

### 原则 2：处理流程可重跑

文档处理不能只做一次，要能 `retry / reprocess`。

### 原则 3：检索片段必须可回源

`chunk` 必须知道自己来自哪个文件、哪一页、哪一段、哪个时间片。

### 原则 4：失败必须可见

任何异常都不能让文档永久停留在 `processing`。

### 原则 5：新格式扩展不破坏旧流程

后续加入图片、音频、视频时，应尽量通过扩展 `extractor / block` 体系来实现。

### 原则 6：当前阶段优先把文本链路做透

不要在 `txt` 链路还不稳定时过早深挖视频和复杂多模态。

---

## 12. 当前阶段的最终目标（给 Codex 的一句话总结）

当前阶段的目标是：

**把 PureLink 从“前端可上传、可检索的原型”，升级为“后端具备标准文件处理流水线、支持文本知识入库、并能为后续引用问答和多模态扩展打基础的知识工作台”。**

---

## 13. 本阶段完成标准（Definition of Done）

以下条件满足后，才算当前阶段真正完成：

1. `txt` 文档上传后可以被稳定保存到服务端
2. 文档点击“开始处理”后不会永久卡在 `processing`
3. 后端处理链路有明确日志和错误回写
4. 文档可以进入 `ready / failed` 等明确状态
5. 文档内容可以被 `chunk` 化并用于检索
6. 检索链路可稳定使用
7. 基础问答链路可基于检索结果调用大模型 API
8. 数据模型已经为 `citation` 和多模态扩展预留空间
9. 整体架构与 FastAPI / PostgreSQL / Redis / Docker 技术栈兼容
10. 后续扩展到 `pdf / docx / image / audio / video` 时不需要推翻当前设计

---

## 14. 接下来开发路线（基于当前实现与策略评审结论）

> 说明：以下路线用于在 `.txt` 最小标准链路已经落地之后继续推进，可视为对前文阶段规划的细化与更新。执行时以“不拆坏现有可运行链路”为前提。

### 14.1 当前项目基线

PureLink 当前已经具备以下基础：

- 前端工作台可用
- `.txt` 上传可用
- `.txt` 已有最小标准处理链路
- `.txt` 处理后会生成数据库 `DocumentChunk`
- 文档状态已形成最小闭环：
  - `uploaded -> processing -> ready / failed`
- `ready` 文档可直接基于数据库 chunk 检索
- 旧链路仍兼容：
  - `parse -> chunk -> embed`
  - 状态为 `indexed`
- 检索层已兼容：
  - `ready`
  - `indexed`

当前对这套策略的定位是：

**它是“先稳定、先可跑、先可扩展”的第一代文本处理与检索方案，不是最终版生产级 RAG。**

因此，接下来的开发路线目标不是推翻重写，而是：

**在不拆坏现有可运行链路的前提下，把 PureLink 渐进式升级为统一的文本知识处理、检索、问答与引用系统，并为多模态与高并发预留架构空间。**

### 14.2 总体开发原则

后续所有实现必须遵循以下原则：

#### 原则 1：不破坏现有 `.txt` 标准链路

现有 `.txt` 链路已经跑通，后续所有抽象和重构都必须以“不破坏现有可用能力”为前提。

#### 原则 2：先统一文本链路，再进入多模态

当前优先级应是：

- `txt`
- `md`
- `pdf`
- `docx`

而不是直接进入：

- 图片 OCR
- 音频
- 视频

#### 原则 3：先统一处理结构，再升级模型能力

先解决：

- `extractor`
- `chunk`
- `metadata`
- 状态机
- `retrieval`

再升级：

- `embedding`
- `hybrid retrieval`
- `rerank`
- `citation-aware QA`

#### 原则 4：保留兼容，但长期收敛

当前双轨是合理过渡：

- `ready`：最小可用检索态
- `indexed`：预计算高效检索态

但长期目标必须是：

**收敛到统一处理入口 + 统一 chunk + 统一检索主路径**

#### 原则 5：每一步都必须可验证

每一部分改动都要有：

- 自动化测试
- 明确状态变化
- 数据库落地验证
- 前端行为验证

### 14.3 接下来的阶段划分

接下来建议按 6 个阶段推进：

1. **Phase 2：统一文本处理链路**
2. **Phase 3：统一 chunk / metadata / retrieval 基础结构**
3. **Phase 4：引入正式 embedding 与 indexed 升级路径**
4. **Phase 5：接入问答主链路与 citation 雏形**
5. **Phase 6：处理链路工程化（ProcessingJob / Worker / Retry）**
6. **Phase 7：为多模态与高并发做准备**

### 14.4 Phase 2：统一文本处理链路

#### 目标

把现有 `.txt` 最小标准链路，扩展为适用于：

- `.txt`
- `.md`
- `.pdf`
- `.docx`

的统一文本处理框架。

#### Phase 2.1：抽出统一文本处理主流程

目标：
不要让 `.txt` 成为孤例，而要让它成为模板。

要做的事：

- 从现有 `document_processing.py` 中提炼统一流程：
  1. 根据 `Document` 定位原始文件
  2. 根据文件类型选择 extractor
  3. 提取文本
  4. 归一化文本
  5. 生成 chunk
  6. 保存 chunk
  7. 更新状态
- 保证 `.txt` 继续通过现有测试
- 路由层只负责调用统一入口，不堆处理细节

输出要求：

- 明确一个统一的 `process_document(...)` 或等价入口
- `.txt` 行为保持不变

验收标准：

- `.txt` 原有标准链路不被破坏
- 主流程可以容纳 `md / pdf / docx` 扩展

#### Phase 2.2：抽出最小 extractor 体系

目标：
把“如何从文件中提取文本”从主流程中拆出来。

要做的事：

- 至少形成以下逻辑边界：
  - `extract_text_from_txt(...)`
  - `extract_text_from_md(...)`
  - `extract_text_from_pdf(...)`
  - `extract_text_from_docx(...)`

要求：

- 输入：文件路径或文档对象
- 输出：纯文本或可继续处理的中间结果
- 异常：抛清晰错误，不要吞掉

验收标准：

- 新增一种文本格式时，不需要重写整个处理主流程

#### Phase 2.3：把 `.md` 迁入标准链路

目标：
`.md` 不再长期依赖旧的 `parse -> chunk -> embed` 兼容路径。

要做的事：

- 后端先支持 `.md` 走统一 `/process`
- 前端逐步把 `.md` 切到统一入口
- Markdown 当前阶段按“轻结构纯文本”处理
- 保留必要兼容 fallback，但不继续扩大旧链路覆盖范围

验收标准：

- `.md` 可以进入：
  - `uploaded -> processing -> ready / failed`
- `.md` 处理后能生成 `DocumentChunk`
- `.md` 可直接进入检索

#### Phase 2.4：接入 `.pdf` 最小文本提取

目标：
支持“文本型 PDF”的最小闭环。

要做的事：

- 选择与当前技术栈兼容的 pdf 文本提取方案
- 实现 pdf extractor
- 提取文本并进入统一 chunk 流程
- 尽量保留页级信息，为后续 citation 预留

当前不做：

- 不处理扫描件 OCR
- 不做复杂版面还原

验收标准：

- 文本型 `.pdf` 可以进入 `ready`
- 处理后能生成 `DocumentChunk`
- `metadata` 中至少能预留页相关信息

#### Phase 2.5：接入 `.docx` 最小文本提取

目标：
支持 Word 文档进入统一处理链路。

要做的事：

- 选择稳定的 docx 提取方案
- 提取段落文本
- 可选保留标题层级的最小语义
- 进入统一 chunk 流程

当前不做：

- 不追求复杂表格或样式还原
- 不做精细文档结构建模

验收标准：

- `.docx` 可以进入 `ready`
- 处理后能生成 `DocumentChunk`

#### Phase 2.6：为文本格式补测试 + 真正执行迁移

要做的事：

- 为 `txt / md / pdf / docx` 成功处理分别补测试
- 为失败场景补测试：
  - 文件不存在
  - 提取失败
  - 空文档
  - 非法文档
- 真正执行本地 PostgreSQL migration：
  - `alembic upgrade head`
- 验证本地开发库与 ORM / migration 一致

验收标准：

- 4 类文本格式至少各有一条成功测试
- 失败场景可进入 `failed`
- 本地数据库 schema 已真实升级

### 14.5 Phase 3：统一 chunk / metadata / retrieval 基础结构

#### 目标

把当前的“最小 chunk 能用”升级为“统一文本格式可共享的 chunk 与 metadata 结构”。

#### Phase 3.1：统一 chunk 最小 schema

目标：
确保 `txt / md / pdf / docx` 生成的 chunk 能被统一检索。

要做的事：

- 统一最小字段，例如：
  - `document_id`
  - `chunk_key`
  - `chunk_index`
  - `chunk_text`
  - `metadata_json`

`metadata_json` 逐步标准化：

- `source_type`
- `char_start`
- `char_end`
- `page_number`（pdf）
- `section_title`（md / docx）
- `heading_path`（后续）
- `source_locator`（后续 citation 用）

验收标准：

- 不同文本格式都能生成统一、可检索、可回源的 chunk

#### Phase 3.2：升级 chunk 切分策略

目标：
从“纯字符长度切分”升级为“结构优先 + 长度兜底”的文本 chunk 策略。

建议顺序：

- `.txt`：段落优先 + 长度兜底
- `.md`：标题 / 段落优先
- `.pdf`：页优先 + 段落
- `.docx`：段落 / 标题优先

要做的事：

- 保留当前固定长度切分作为 fallback
- 增加更自然的切分边界
- 不要一开始上复杂 semantic chunking

验收标准：

- chunk 的语义完整性比当前更好，同时不破坏稳定性

#### Phase 3.3：让 retrieval 正式围绕标准 chunk 收口

目标：
减少双轨检索分叉的复杂度。

要做的事：

- 明确 retrieval 的主输入逐步转向 `DocumentChunk`
- 继续兼容旧 `indexed` 文档，但避免分支继续膨胀
- 对 `ready` 和 `indexed` 明确角色：
  - `ready`：最小可用检索态
  - `indexed`：正式高效检索态

验收标准：

- 检索逻辑更清晰，不再无序增长兼容分支

### 14.6 Phase 4：引入正式 embedding 与 indexed 升级路径

#### 目标

让当前的 `hashed_bow_v1` 从“主方案”降级为“本地 fallback / 过渡方案”，逐步接入正式语义 embedding。

#### Phase 4.1：明确 embedding provider 抽象

目标：
不要让 embedding 逻辑散在检索和处理代码里。

要做的事：

- 抽出可配置 provider，例如：
  - `local_hashed_bow`
  - `external_embedding_api`
  - `local_embedding_model`（后续可选）

验收标准：

- 后续切换 embedding 不需要重写整个检索链路

#### Phase 4.2：把 `ready -> indexed` 变成正式升级路径

目标：
让 `ready` 成为即时可用态，而不是长期主态。

要做的事：

- 文档处理完成后先进入 `ready`
- 后续异步或二阶段执行 embedding / index
- 完成后升级为 `indexed`
- 检索优先使用 `indexed`

验收标准：

- `ready` 可立即使用
- `indexed` 提供更高效检索
- 两者关系清晰

#### Phase 4.3：逐步接入真实语义 embedding

目标：
提升检索质量，特别是中文语义召回能力。

要做的事：

- 先接入一个可配置的外部 embedding API
- 保留 `hashed_bow_v1` 作为 fallback
- 为 query embedding 和 chunk embedding 统一接口

当前不做：

- 不急着上复杂多模型编排
- 不急着本地大模型 embedding

验收标准：

- 新链路可以切换到真实语义 embedding，且不破坏 fallback

### 14.7 Phase 5：接入问答主链路与 citation 雏形

#### 目标

把“检索能用”推进到“可以做基础问答，并逐步带来源依据”。

#### Phase 5.1：建立最小问答链路

目标：
实现标准文本 RAG 的最小可用版本。

要做的事：

建立链路：

用户提问  
→ query 预处理  
→ 检索相关 chunk  
→ 组装上下文  
→ 调用大模型 API  
→ 返回 answer

验收标准：

- 至少一类文本知识库可完成：
  上传 → 处理 → 检索 → 回答

#### Phase 5.2：设计 citation 基础结构

目标：
为“带来源的回答”打基础。

要做的事：

- 设计 `Citation` 或等价结构，至少预留：
  - `document_id`
  - `chunk_id`
  - `snippet`
  - `page_number / section_title`
  - `source_locator`

验收标准：

- 后续返回 citation 时不需要再推翻 chunk / metadata 设计

#### Phase 5.3：返回最小来源依据

目标：
先做 citation 雏形，不求一步到位。

第一步返回内容：

- 文件名
- `chunk snippet`
- `document_id`
- 可选 `page_number / section_title`

验收标准：

- 问答结果不再只有 `answer`，而有基础来源依据

### 14.8 Phase 6：处理链路工程化（ProcessingJob / Worker / Retry）

#### 目标

让处理链路从“同步函数式实现”升级为“标准化可管理流水线”。

当前状态：

- M13 基础版已完成
- 已落地 `ProcessingJob` 模型、状态枚举、任务查询接口
- 已把统一 `/process` 接到 job 主路径，支持步骤记录、失败回写、`retry-process`、`reprocess`
- 已在 Docker + PostgreSQL 真库完成 live smoke 验证
- 尚未完成的部分是：把处理彻底从请求链路中解耦到独立 worker / queue

#### Phase 6.1：引入 ProcessingJob

目标：
把“文档处理过程”从 document 状态中部分独立出来。

当前状态：已完成基础版

当前已落字段：

- `document_id`
- `triggered_by_id`
- `previous_job_id`
- `job_type`
- `trigger_type`
- `status`
- `current_step`
- `attempt_number`
- `worker_name`
- `error_message`
- `started_at`
- `finished_at`

验收标准：

- 文档处理过程有独立任务追踪能力

#### Phase 6.2：把处理从请求链路中解耦

目标：
上传接口和处理任务分离。

当前状态：已完成基础版本，仍需继续工程化

现状说明：

- 当前 `/process` 已经先创建 `ProcessingJob` 再执行处理
- 目前执行端是 Python inline worker，不再是“接口只改 document 状态”
- 真正的 `BackgroundTasks / Redis 队列 / 独立 worker` 仍是下一步

要做的事：

- 上传完成后投递 job
- worker 执行处理
- 前端查询 `job / document` 状态

当前可接受方案：

- FastAPI `BackgroundTasks`
- Python worker
- Redis 队列（后续）

验收标准：

- 文档处理不再强耦合在单个请求中

#### Phase 6.3：支持 retry / reprocess

目标：
让失败处理和升级处理有正式入口。

当前状态：已完成基础版

要做的事：

- 失败文档可重试
- 已处理文档可重处理
- 状态流转清晰
- `chunk / index` 重建规则清晰

验收标准：

- 处理流程具备可重跑能力

### 14.9 Phase 7：为多模态与高并发做准备

#### 目标

不马上做完整多模态，但提前做好结构准备。

#### Phase 7.1：为图片 / 扫描件预留 extractor 扩展位

目标：
后续可接：

- image OCR
- scanned pdf OCR

要做的事：

- extractor 体系可扩展到非纯文本来源
- metadata 支持 `region / bbox / page locator`

#### Phase 7.2：为音频 / 视频预留时间轴结构

目标：
后续可支持：

- 音频转写
- 视频转写
- 时间戳引用

要做的事：

- metadata 预留：
  - `start_time`
  - `end_time`
  - `source_locator`

#### Phase 7.3：为高并发和存储升级预留架构

目标：
后续平滑升级，不推翻现有系统。

方向：

- 文件存储从本地磁盘或 Docker volume 升级到 MinIO / S3
- worker 独立服务化
- Redis 队列
- Go 组件后续介入：
  - 高并发上传
  - 任务调度
  - 状态通知

### 14.10 推荐执行顺序

请按下面顺序推进，不要跳跃：

1. 先完成统一文本处理链路  
   对应：Phase 2
2. 再统一 chunk / metadata / retrieval 基础结构  
   对应：Phase 3
3. 再接正式 embedding 与 indexed 升级路径  
   对应：Phase 4
4. 再推进问答与 citation 雏形  
   对应：Phase 5
5. 再做处理链路工程化  
   对应：Phase 6
6. 最后为多模态和高并发做准备  
   对应：Phase 7

### 14.11 当前最重要的短期目标（优先执行）

如果要压缩成近期最重要的 5 项，请优先做：

1. 把 `.md / .pdf / .docx` 纳入统一文本处理链路
2. 统一 chunk 与 metadata 结构
3. 把 retrieval 的主输入逐步收口到 `DocumentChunk`
4. 设计 embedding provider，并规划 `ready -> indexed` 升级路径
5. 建立最小问答链路，为 citation 做结构准备

### 14.12 最终目标（一句话总结）

接下来的开发路线目标是：

**在保持当前 `.txt` 标准链路稳定可用的前提下，把 PureLink 渐进式升级为一个统一处理文本知识资产、支持标准 RAG 检索问答、可逐步返回来源依据、并为多模态与高并发扩展预留基础结构的知识工作台。**
