# PureLink

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688.svg)
![Next.js](https://img.shields.io/badge/Next.js-frontend-black.svg)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)

PureLink 是一个**本地优先、云端兼容的自部署 AI 知识库系统**，适合个人、小团队、实验室、项目组服务器或用户自己的云服务器部署。

PureLink is a local-first, cloud-ready, self-hosted AI knowledge workspace for individuals and small teams.

你需要自己部署服务、管理数据，并通过 `.env` 配置自己的 `LLM_PROVIDER`、`EMBEDDING_PROVIDER`、`OCR_PROVIDER`、`ASR_PROVIDER` 和 `RERANKER_PROVIDER`。

## PureLink 是什么？

PureLink 把文档和多媒体文件变成可检索、可问答、可引用来源的知识库，核心路径是：

```text
启动系统 -> 注册登录 -> 创建知识库 -> 上传文件 -> 自动准备 -> 提问 -> 查看 citation -> 打开 source preview
```

适合的部署场景：

- 本机个人部署
- 小团队内网部署
- 实验室 / 项目组服务器部署
- 用户自行部署到云服务器

## 核心能力

- 个人知识库和团队知识库
- 团队邀请码、成员管理、管理员审核
- 上传后自动准备文档，审核通过后自动进入处理
- 支持 `.txt`、`.md`、`.pdf`、`.docx`、图片 OCR、音频转写、视频转写
- Hybrid retrieval、轻量 rerank、问答、citation
- 支持 `source_locator` / `preview_target` 的来源预览
- 默认本地 demo 模式不需要外部 API key
- Docker Compose 一键启动 PostgreSQL、Redis、FastAPI API、Python worker、Next.js frontend

## 快速开始

```bash
git clone https://github.com/pmk915/purelink.git
cd purelink
cp .env.example .env
docker compose up -d --build
```

打开：

- 前端：`http://localhost:3000`
- API 文档：`http://localhost:8000/docs`
- API health：`http://localhost:8000/api/v1/health`
- Provider status：`http://localhost:8000/api/v1/system/providers`

检查本地服务：

```bash
make check
```

停止服务：

```bash
docker compose down
```

首次构建会安装 OCR、媒体处理和 ASR 依赖，耗时会更长。

## 5 分钟 Demo

1. 克隆仓库。
2. 执行 `cp .env.example .env`。
3. 执行 `docker compose up -d --build`。
4. 打开 `http://localhost:3000`。
5. 注册一个用户。
6. 创建个人知识库。
7. 上传 `examples/text/playbook.txt`。
8. 等待文档变成“可问答”。
9. 提问：`What is this document about?`
10. 点击 citation，进入来源预览页面。

默认本地模式可以不配置任何外部 API key 跑通这个 demo。配置真实 LLM 和 Embedding Provider 后，回答质量和检索效果会更好。

`examples/` 目录提供小型 demo 文件，仅用于本地测试。音频和视频样例本轮不提交，测试 ASR 时请自行准备短文件。

## Provider 配置指南

PureLink 的 provider 都通过 `.env` 配置。默认模式优先保证“可以本地跑通”，外部模型模式用于更好的真实效果。

### 默认本地模式

默认配置：

```env
LLM_PROVIDER=heuristic
EMBEDDING_PROVIDER=local_hashed_bow
OCR_PROVIDER=tesseract
ASR_PROVIDER=vosk
RERANKER_PROVIDER=local_rule_reranker
```

说明：

- `heuristic`：本地演示问答，不需要 `LLM_API_KEY`。
- `local_hashed_bow`：本地 fallback embedding，不需要 `EMBEDDING_API_KEY`。
- `tesseract`：用于图片 OCR 和扫描版 PDF OCR。
- `vosk`：用于音频和视频转写，需要本地模型路径存在。
- `local_rule_reranker`：轻量规则 rerank，用于改善排序稳定性。

默认模式适合本地 demo 和开发联调，不代表最终高质量问答效果。真实使用建议配置外部 LLM 和 Embedding Provider。

### 配置外部 LLM Provider

OpenAI-compatible 示例：

```env
LLM_PROVIDER=openai_compatible
LLM_API_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-chat-model
LLM_TIMEOUT_SECONDS=30
```

注意：

- `LLM_API_KEY` 不要提交到 Git。
- 当前调用格式是 OpenAI-compatible `chat/completions`。
- 如果使用 DashScope、OpenAI 兼容网关或自建代理，把 `LLM_API_BASE_URL` 填成对应的 `/v1` base URL。
- 缺少 `LLM_API_BASE_URL`、`LLM_API_KEY` 或 `LLM_MODEL` 时，`/api/v1/system/providers` 会显示配置未完成。

### 配置外部 Embedding Provider

OpenAI-compatible 示例：

```env
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_API_BASE_URL=https://api.example.com/v1
EMBEDDING_API_KEY=your-api-key
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_TIMEOUT_SECONDS=30
```

说明：

- Embedding 用于 `indexed` 路径和语义检索。
- `EMBEDDING_API_KEY` 不要提交到 Git。
- 外部 Embedding Provider 需要兼容 OpenAI `embeddings` API。
- 缺少 `EMBEDDING_API_BASE_URL`、`EMBEDDING_API_KEY` 或 `EMBEDDING_MODEL` 时，索引和语义检索会失败。

### OCR Provider 配置

```env
OCR_PROVIDER=tesseract
OCR_LANG=eng
```

说明：

- OCR 用于图片 OCR。
- OCR 也用于扫描版 PDF 的 fallback。
- Docker 镜像默认安装 `tesseract` 和英文语言包。
- 如果容器中缺少 `tesseract` 或对应语言包，OCR 会失败。

### ASR Provider 配置

```env
ASR_PROVIDER=vosk
ASR_MODEL_PATH=/app/models/vosk
```

说明：

- ASR 用于音频转写。
- 视频会先通过 `ffmpeg` 抽取音频，再使用 ASR 转写。
- 如果 `ASR_MODEL_PATH` 不存在，音频和视频处理会失败。
- 如果 `ffmpeg` 不可用，音频转换和视频抽音会失败。

### Reranker Provider 配置

```env
RERANKER_PROVIDER=local_rule_reranker
```

说明：

- 当前默认使用轻量规则 rerank。
- 它可以提升 hybrid retrieval 后的排序稳定性。
- external reranker 还不是当前主路径。

### 修改 Embedding Provider 后需要重新索引

如果你修改了 `EMBEDDING_PROVIDER` 或 `EMBEDDING_MODEL`，已有 `indexed` 文档仍然使用旧索引。为了让旧文档使用新的 embedding provider，需要重新索引。

可选方式：

- 在前端对失败或需要更新的文档重新准备。
- 调用 `/embed` 相关接口手动重建索引。
- 重新处理文档，让它重新进入 `ready -> indexed` 路径。

如果看到 provider/model 不匹配错误，通常说明当前配置和旧 index artifact 的 provider 或 model 不一致。

### 常见 Provider 配置错误

- 问答质量很基础：仍在使用 `LLM_PROVIDER=heuristic`。
- 检索语义效果弱：仍在使用 `EMBEDDING_PROVIDER=local_hashed_bow`。
- 外部 LLM 报错：检查 `LLM_API_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。
- 外部 embedding 报错：检查 `EMBEDDING_API_BASE_URL`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL`，并确认切换后重新索引。
- 图片或扫描 PDF OCR 失败：检查 `OCR_PROVIDER=tesseract`、`OCR_LANG` 和容器内语言包。
- 音频或视频失败：检查 `ASR_MODEL_PATH` 和 `ASR_FFMPEG_COMMAND`。

## 支持的文件类型

| 类型 | 格式 | 说明 |
| --- | --- | --- |
| Text | `.txt`, `.md` | 最适合首次 demo |
| Office / PDF | `.docx`, `.pdf` | 文本 PDF 直接抽取；扫描 PDF 走 OCR fallback |
| Image | `.png`, `.jpg`, `.jpeg` | 依赖 OCR Provider |
| Audio | `.mp3`, `.wav`, `.m4a` | 依赖 ASR Provider 和模型 |
| Video | `.mp4`, `.mov`, `.m4v` | 先抽音，再走 ASR |

M27 不继续增加新格式，重点是 provider 配置体验、中文文档和自部署可诊断性。

## 架构

```text
Browser
  -> Next.js frontend
  -> FastAPI API
  -> PostgreSQL metadata
  -> Redis processing queue
  -> Python worker
  -> local file storage
  -> DocumentChunk / index artifacts
  -> retrieve / ask / citation / preview
```

团队审核规则：

- 个人上传：自动准备。
- 团队管理员上传：自动通过并准备。
- 团队成员上传：先等待管理员审核。
- 被拒绝的团队文档不会进入检索。

## Main Path vs Legacy Compatibility

当前主路径：

```text
upload
-> ProcessingJob(document_process)
-> extract / OCR / ASR
-> DocumentChunk
-> ready
-> ProcessingJob(document_index)
-> indexed
-> retrieve / ask / citation / preview
```

历史兼容和调试路径仍然保留：

- `parse`
- `chunk`
- `embed`
- old task APIs
- `worker-go`

新功能应优先走主路径。`worker-go` 当前不是主生产 worker。

## 故障排查

常用命令：

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f redis
docker compose down
docker compose up -d --build api worker
make check
```

常见问题：

- WSL 中找不到 Docker：启用 Docker Desktop WSL integration。
- 后端改动未生效：执行 `docker compose up -d --build api worker`。
- 文档一直“准备中”：检查 `docker compose logs -f worker` 和 Redis。
- Provider 配置是否正确：打开 `/api/v1/system/providers` 或执行 `make check`。
- 默认模式回答较弱：配置外部 LLM 和 Embedding Provider。

更多排查路径见：[docs/troubleshooting.md](docs/troubleshooting.md)。

## 验证

后端测试：

```bash
pytest -q
```

前端检查：

```bash
cd frontend
npm run lint
npm run build
```

Smoke / E2E：

```bash
make smoke
make e2e
```

## 项目结构

```text
purelink/
├── app/                    # FastAPI app, models, schemas, services, workers
├── alembic/                # Database migrations
├── docs/                   # 中文指南和故障排查
├── examples/               # 本地 demo 小文件
├── frontend/               # Next.js frontend and Dockerfile
├── scripts/                # E2E and stack check scripts
├── tests/                  # pytest test suite
├── worker-go/              # Legacy / experimental Go worker
├── data/                   # Local runtime artifacts
├── docker-compose.yml      # Full local stack
├── Dockerfile              # API / worker image
└── Makefile                # Common commands
```

## Roadmap

Short-term:

- 完善本地部署体验
- 完善 provider 配置体验
- 增加 demo script
- 优化用户可见状态文案
- 改善失败重试体验

Mid-term:

- MinIO / S3 对象存储
- 云服务器部署指南
- 管理员调试视图
- 更强 provider 支持
- 更完善的权限与审核体验

Long-term:

- Kubernetes / Helm
- 多 worker 横向扩容
- 监控告警
- 更强多模态理解
- 更完整的企业自部署能力

## 相关文档

- [PLAN.md](PLAN.md)：阶段计划和路线
- [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)：开发记录
- [DEV_COMMANDS.md](DEV_COMMANDS.md)：本地常用命令
- [frontend/README.md](frontend/README.md)：前端局部说明
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献说明
- [LICENSE](LICENSE)：MIT license

## Contributing

欢迎提交 issue 和 pull request。较大改动请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

建议：

- 保持 Docker stack 可运行。
- 修改后端行为时补测试。
- 修改 `frontend/` 时运行 lint/build。
- 新文档优先中文说明。
- 新文档处理能力优先走 main path，不继续扩展 legacy path。

## License

PureLink 使用 [MIT License](LICENSE)。
