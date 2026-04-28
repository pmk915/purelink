# 故障排查

本文面向 PureLink 本地 Docker Compose 和自部署场景。命令、配置项和 API 路径保持原样。

## 快速检查

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f redis
docker compose down
docker compose up -d --build api worker
make check
```

`make check` 会检查：

- API health
- PostgreSQL
- Redis
- worker
- frontend
- `/api/v1/system/providers`

Provider status 输出含义：

- `[OK]`：当前配置可用。
- `[WARN]`：服务可运行，但某类能力可能不可用，例如 `ASR_MODEL_PATH` 不存在。
- `[FAIL]`：关键配置不完整，例如外部 LLM 缺少 `LLM_API_KEY`。

## Docker / WSL

### 找不到 `docker`

如果在 WSL 2 中看到 `docker: command not found`，需要安装 Docker Desktop，并在 Docker Desktop 设置中为当前 WSL distro 开启 WSL integration。

### `docker compose` 不可用

PureLink 默认使用 Docker Compose v2：

```bash
docker compose
```

如果你的环境只有 `docker-compose`，可以临时这样运行：

```bash
COMPOSE=docker-compose make check
```

### 后端改动没有生效

重新构建 API 和 worker：

```bash
docker compose up -d --build api worker
```

如果修改了 `NEXT_PUBLIC_API_BASE_URL`，还需要重建 frontend：

```bash
docker compose up -d --build frontend
```

## Worker

### 文档一直显示“准备中”

先看服务状态：

```bash
docker compose ps
```

再看 worker 日志：

```bash
docker compose logs -f worker
```

检查 Redis：

```bash
docker compose logs -f redis
docker compose exec redis redis-cli ping
```

如果文档已经失败，可以在前端文档卡片上重试，或重新上传。

### Redis 有任务但 worker 没消费

重启 worker：

```bash
docker compose up -d --build worker
docker compose logs -f worker
```

确认 worker 容器内的 `REDIS_URL` 指向 Compose 内部 Redis：

```bash
docker compose exec worker env | grep REDIS_URL
```

## LLM Provider

### 默认模式下回答为什么比较简单？

默认配置是：

```env
LLM_PROVIDER=heuristic
```

`heuristic` 是本地演示模式，不调用外部大模型。它能跑通 demo，但回答质量有限。

更好的回答质量需要配置 OpenAI-compatible LLM：

```env
LLM_PROVIDER=openai_compatible
LLM_API_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-chat-model
LLM_TIMEOUT_SECONDS=30
```

### 外部 LLM 报错

检查：

- `LLM_API_BASE_URL` 是否是正确的 `/v1` base URL
- `LLM_API_KEY` 是否填写
- `LLM_MODEL` 是否存在
- 当前服务器是否能访问 provider endpoint
- provider 是否兼容 OpenAI `chat/completions`

可以通过接口查看状态：

```bash
curl http://localhost:8000/api/v1/system/providers
```

## Embedding Provider

### 默认检索效果为什么比较基础？

默认配置是：

```env
EMBEDDING_PROVIDER=local_hashed_bow
```

`local_hashed_bow` 是本地 fallback，适合 demo 和开发，不代表真实语义 embedding 效果。

更好的语义检索需要配置 OpenAI-compatible embedding：

```env
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_API_BASE_URL=https://api.example.com/v1
EMBEDDING_API_KEY=your-api-key
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_TIMEOUT_SECONDS=30
```

### 切换 embedding 后旧文档为什么没有变化？

已有 `indexed` 文档使用旧 index artifact。修改 `EMBEDDING_PROVIDER` 或 `EMBEDDING_MODEL` 后，需要重新索引旧文档。

可选方式：

- 对文档重新准备
- 调用 `/embed` 相关接口重建索引
- 重新处理文档，让它重新进入 `ready -> indexed`

### provider/model 不匹配是什么意思？

当前 `.env` 中的 embedding provider 或 model，与旧 index artifact 里记录的 provider 或 model 不一致。为避免混用不同向量空间，PureLink 会提示不匹配。解决方式是重新索引。

## OCR Provider

### 图片 OCR 或扫描 PDF OCR 失败

默认配置：

```env
OCR_PROVIDER=tesseract
OCR_LANG=eng
OCR_TESSERACT_COMMAND=tesseract
```

检查：

```bash
docker compose logs -f worker
docker compose exec worker tesseract --version
```

如果使用中文 OCR，需要确认容器中安装了对应语言包，并把 `OCR_LANG` 改成对应值。

### `tesseract` 不可用

Docker 镜像默认安装 `tesseract`。如果你在宿主机手动运行后端，需要自己安装 `tesseract`，或把 `OCR_TESSERACT_COMMAND` 设置为可执行文件完整路径。

## ASR Provider

### 音频或视频处理失败

默认配置：

```env
ASR_PROVIDER=vosk
ASR_MODEL_PATH=/app/models/vosk
ASR_FFMPEG_COMMAND=ffmpeg
```

检查 Vosk 模型：

```bash
docker compose exec worker ls -la /app/models/vosk
```

检查 ffmpeg：

```bash
docker compose exec worker ffmpeg -version
```

### Vosk 模型路径不存在

`make check` 会把这种情况显示为 `[WARN]`，因为它不会影响文本知识库 demo，但音频和视频处理会失败。

如果你挂载自己的模型，需要确保 `ASR_MODEL_PATH` 是 worker 容器内部可见的路径。

### `ffmpeg` 不可用

Docker 镜像默认安装 `ffmpeg`。宿主机手动运行时，需要自己安装 `ffmpeg`，或把 `ASR_FFMPEG_COMMAND` 设置为可执行文件完整路径。

## Reranker Provider

默认配置：

```env
RERANKER_PROVIDER=local_rule_reranker
```

当前 `local_rule_reranker` 是轻量规则 rerank，用于提升 hybrid retrieval 后的排序稳定性。external reranker 还不是当前主路径。

## Provider Status 接口

Provider 状态接口：

```http
GET /api/v1/system/providers
```

返回中不会包含 API key 或 secret，只会显示：

- provider 名称
- 是否配置完成
- 是否需要 API key
- API key 是否已填写的布尔值
- model 名称
- ASR 模型路径是否存在
- 简短 message

示例：

```bash
curl http://localhost:8000/api/v1/system/providers
```

## 常见命令

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f redis
docker compose down
docker compose up -d --build api worker
docker compose up -d --build frontend
make check
```
