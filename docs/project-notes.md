# 项目复盘与面试说明

## 1. 项目为什么做

团队知识常常散落在文档里，但普通聊天机器人无法保证来源可靠。PureLink Core 的目标，是把文档处理成可检索知识块，并返回带来源的答案。

## 2. 核心业务问题

- 用户 / 团队知识库如何隔离？
- 文件上传后如何异步处理？
- 如何避免重复文件重复处理？
- 如何保证失败可追踪？
- 如何避免大模型无依据回答？

## 3. 技术取舍

### 为什么不默认做多模态？

因为当前项目的主问题是文本知识库，不是通用多模态助手。默认带上 OCR / ASR / 视频 / 多模态依赖，会显著增大镜像体积和部署复杂度。

### 为什么不用 PyTorch 默认部署？

默认部署需要轻量、稳定、可自部署。`PyTorch` 和 `sentence-transformers` 作为默认依赖会明显增加镜像体积和构建成本。

### 为什么使用 fastembed？

`fastembed` 能提供本地语义检索能力，同时避免默认引入 `PyTorch`。对于 PureLink Core 的目标，它在质量和体积之间是合适的折中。

### 为什么使用 Redis + Worker？

上传接口不应该同步做文本提取、chunk 和 embedding。Redis + Worker 可以把入口请求和后台处理解耦，也更适合后续扩展 retry / timeout / 多 worker。

### 为什么 citations 由后端生成？

因为来源追踪应该依赖真实 retrieval results，而不是让大模型自由编写。这样能保证每条 citation 都能落到真实 chunk。

### 为什么默认只支持 txt / md / docx / 普通 PDF？

这是为了保持边界清晰。默认能力越收敛，越容易保证：

- 处理稳定性
- 部署简单
- 测试覆盖
- 文档真实反映当前能力

## 4. 可被追问的问题

### `ProcessingJob` 为什么单独建表？

`Document` 记录文件当前状态，`ProcessingJob` 记录一次处理任务。这样才能支持重复处理、重试、超时、失败定位和任务级追踪。

### worker 如何避免重复处理？

worker 在处理前会通过数据库状态更新抢占 `queued -> processing`。只有抢占成功的 worker 才继续执行。

### sha256 去重有什么权限边界？

当前只在同一个 knowledge base 内去重，不做跨 knowledge base 全局复用，避免权限泄露和跨团队数据混用。

### index metadata 为什么重要？

因为 embedding provider / model / dimension / normalize 变化后，会导致向量空间不兼容。metadata 是判断是否需要 `reindex` 的基础。

### embedding provider 改了为什么要 reindex？

旧文档的向量是按旧 provider / model 生成的。直接混用会让同一个 knowledge base 进入混合向量空间，检索结果不可靠。

### `no reliable source` 是怎么判断的？

当没有检索结果，或者最高检索分低于 `RETRIEVAL_MIN_SCORE` 时，系统返回固定提示并让 `citations=[]`。

### team KB 怎么避免跨团队检索？

检索入口会先做知识库作用域和成员权限校验，只会在当前用户可访问的 knowledge base 文档范围内构建检索候选集。
