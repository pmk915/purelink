# PureLink 开发计划

## 项目定位

PureLink 是一个面向团队内部文档管理的 AI 知识库问答与任务助手平台。

当前技术路线：

- 后端：FastAPI
- 数据库：PostgreSQL
- 缓存：Redis（后续按需接入）
- AI：Embedding + 向量库 + RAG
- 部署：Docker / Docker Compose
- 前端：Next.js App Router

## 当前状态

已完成里程碑：

- `M1`：API 结构规范化与应用入口整理
- `M2`：数据库底座与核心业务实体
- `M2.5`：数据库迁移与本地验证链路
- `M3`：最小认证系统
- `M4`：个人知识库 CRUD
- `M4.5`：团队域模型
- `M4.6`：团队创建、邀请码、入队与成员查看
- `M4.7`：团队知识库
- `M5.1`：文档上传与提交记录
- `M5.2`：团队文档审核接口
- `M6.1`：文档解析最小闭环
- `M6.2.1`：文档解析任务机制
- `M6.2.2`：Go parse worker 最小实现
- `M6.2.3`：任务防重与 Go worker 验证
- `M7.1`：文档切块与检索准备层
- `M7.2`：最小 embedding 与检索层
- `M7.3`：最小问答接口
- `M8.1`：正式 LLM 接入抽象与 provider 切换
- `M8.2`：问答会话与消息持久化
- `M9.1`：统一文档处理任务链
- `M9.2`：Go chunk worker
- `M9.3`：Go worker 接手 embed / index
- `M10.1`：部署与运行收口
- `M10.2`：Makefile、CI 与 smoke 收口
- `F1`：前端 MVP、双语切换、联调与文档收口

当前已具备能力：

- 用户注册、登录、JWT 鉴权、当前用户查询
- 个人知识库 CRUD 与归属隔离
- 团队创建、邀请码生成、入队、成员查看
- 团队知识库 CRUD 与 admin / member 权限区分
- 个人文档上传、团队文档提交、团队审核流
- 个人与团队文档的 parse / chunk / embed / retrieve / ask 闭环
- `document_tasks` + Go worker 的 parse / chunk / embed / index 异步链路
- 会话与消息持久化、citations 保存
- OpenAI-compatible LLM provider 切换能力
- Docker Compose 一键启动
- Bash E2E、Makefile、GitHub Actions CI / smoke
- Next.js 前端 MVP 与中英文切换

## 当前阶段判断

当前项目已经不再处于“从零搭后端底座”的阶段，而是进入了：

`可运行原型收口 + 前端产品化打磨 + 稳定性增强`

当前最重要的事情，不是继续快速堆新业务点，而是把已经形成的全链路体验、调试能力和可验证性补稳。

## 当前阶段目标

当前阶段的核心目标：

1. 让前后端主链路更稳定、更容易手动调试
2. 让文档处理链在失败时更容易观察和恢复
3. 让 PostgreSQL / 迁移 / Docker / CI 这条工程链更可信
4. 在不破坏现有闭环的前提下，继续提升检索与问答质量

当前阶段优先级：

1. 稳定性与可观测性
2. 前端产品化与交互细节
3. PostgreSQL 迁移验证与回滚验证
4. 检索与问答质量
5. 生产化底座预留

## 路线图

### M10.3 稳定性与可观测性

**Goal**

把当前已经可用的上传、处理、检索、问答链路补成“可诊断、可恢复、可解释”的状态。

**Scope**

- 强化 parse / chunk / embed / index 的日志与错误暴露
- 明确任务链和同步处理链的边界说明
- PostgreSQL 上补真实的迁移升级验证
- 对关键迁移逐步补 `upgrade -> downgrade -> upgrade` 验证
- 补充更清晰的故障排查文档和本地验证步骤

**Out of Scope**

- 新业务实体
- 新权限模型
- 新的异步基础设施

**Acceptance Criteria**

- 至少一轮关键迁移在 PostgreSQL 上完成 `upgrade head` 验证
- 至少一类关键迁移完成 `upgrade -> downgrade -> upgrade` 验证
- 文档处理失败时，日志和接口返回足够定位问题
- README / test.md / DEVELOPMENT_LOG 中的运行和排查说明与实际行为保持一致

### M10.4 前端产品化打磨

**Goal**

把当前前端从“能演示”继续推进到“更像正式产品原型”。

**Scope**

- 工作台、知识库、团队、审核、会话页面的交互细节打磨
- 上传、处理、检索、问答的状态反馈统一
- 空状态、错误态、加载态进一步收口
- 中英双语文案一致性检查
- 减少开发者视角提示，强化用户视角表达

**Out of Scope**

- 重做设计系统
- 复杂动效系统
- 新的大型业务模块

**Acceptance Criteria**

- 用户可以从前端完成注册、登录、创建知识库、上传文档、处理、检索、问答
- 主要页面不再暴露明显的开发态提示
- 上传与处理失败时，页面能给出明确、可理解的错误反馈
- 主要页面的中英文文案一致且可切换

### M11 检索与问答质量提升

**Goal**

在保持现有最小闭环的前提下，提升 retrieval 和 answer 的质量。

**Scope**

- 更稳定的 embedding / 检索策略
- 可选 rerank 或更合理的 top-k 策略
- prompt 构造与 citations 呈现优化
- heuristic 与 real LLM provider 的体验对齐

**Out of Scope**

- 多 agent 编排
- 复杂工作流引擎
- 重写现有检索接口

**Acceptance Criteria**

- retrieval 结果稳定覆盖主要文本片段
- ask 结果能继续复用现有 citations 结构
- provider 切换不破坏现有 `/ask` 接口
- 团队问答继续严格受 `approved + indexed` 约束

### M12 生产化底座预留

**Goal**

为后续从本地演示原型走向更稳的部署形态留出清晰边界。

**Scope**

- 本地文件存储向对象存储迁移的边界预留
- Redis / 队列系统的接入边界设计
- 环境变量、部署文档和发布流程收口
- 更清晰的 worker / API / storage 职责分层

**Out of Scope**

- 立刻引入完整微服务体系
- 立刻切换到重量级消息队列

**Acceptance Criteria**

- 文件存储路径与业务语义分离清晰
- `document_tasks` 模型仍可作为异步边界核心
- Docker / Compose / CI / README 保持一致
- 后续接入 Redis、对象存储或外部向量库时不需要推翻现有主链路

## 当前约束

- 保持现有个人知识库与团队知识库逻辑继续可用
- 保持前端手动处理链和 `document_tasks` 异步链都可用，且语义清晰
- 不提前引入厚重的 repository 抽象
- 服务层继续保持薄且业务导向
- 权限判断以所有权和成员关系为中心
- `owner_id`、`team_id`、审核结果等特权字段不能由前端直接决定
- 文档处理失败必须能回写明确状态，不能长期停在中间态
- 结构性迁移至少保证 PostgreSQL 上的 `upgrade head` 可验证
- 关键迁移逐步补 `upgrade -> downgrade -> upgrade` 验证
- 文档、README、测试手册必须与真实系统行为保持一致

## 下一步建议

建议优先进入 `M10.3 稳定性与可观测性`，然后再做 `M10.4 前端产品化打磨`。

原因：

- 当前主链路已经打通，继续堆新功能的收益低于把现有链路补稳
- 近期开发中已经出现过上传链路、处理状态、联调方式和 worker 语义混淆的问题
- 先补稳定性、日志、迁移验证和文档一致性，后续继续做 retrieval / QA 优化会更安全
- 当前前端已经可用，下一步更适合做产品化打磨，而不是再快速扩业务面
