# 故障排查

本文面向 PureLink `Core` 版本：默认只处理 `.txt`、`.md`、`.docx` 和普通文本型 `.pdf`。命令、配置项和 API 路径保持原样。

## 快速检查

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f redis
docker compose down
docker compose up -d --build api worker frontend
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
- `[FAIL]`：关键配置不完整，例如外部 LLM 缺少 `LLM_API_KEY`。
- `OCR_PROVIDER=disabled`、`ASR_PROVIDER=disabled` 在默认 Core 配置下会显示为 `[OK]`，不是 warning。

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

确认 Redis 可用：

```bash
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

### 如何配置外部 LLM？

```env
LLM_PROVIDER=openai_compatible
LLM_API_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-chat-model
LLM_TIMEOUT_SECONDS=30
```

检查：

- `LLM_API_BASE_URL` 是否是正确的 `/v1` base URL
- `LLM_API_KEY` 是否填写
- `LLM_MODEL` 是否存在
- 当前服务器是否能访问 provider endpoint

### DeepSeek 为什么一直答不出来？

如果你使用 DeepSeek，不要把：

```env
LLM_PROVIDER=deepseek
```

误当成旧版本里不支持的自定义值。当前 Core 已经支持 `deepseek` provider，并会按 OpenAI-compatible 的 `chat/completions` 格式请求：

```env
LLM_PROVIDER=deepseek
LLM_API_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your-deepseek-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key
LLM_MODEL=deepseek-v4-pro
LLM_REASONING_EFFORT=high
LLM_THINKING_ENABLED=true
```

重点检查：

- `LLM_API_BASE_URL` 是否为 `https://api.deepseek.com`
- `LLM_API_KEY` 或 `DEEPSEEK_API_KEY` 是否至少配置了一个
- `LLM_MODEL` 是否填写了真实模型名
- API key 是否正确
- 修改 `.env` 后是否已经重启 `api`

## Embedding Provider

### 默认检索为什么不是最轻量 fallback？

当前 Core 默认配置是：

```env
EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

这会在本地提供真实语义 embedding。首次运行下载模型是正常现象。

### 不想下载模型怎么办？

改成：

```env
EMBEDDING_PROVIDER=local_hashed_bow
EMBEDDING_MODEL=
```

这样更轻，但检索质量会下降。

### 切换 embedding 后旧文档为什么没有变化？

已有 `indexed` 文档仍然使用旧 index artifact。修改 `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL` 或 `EMBEDDING_NORMALIZE` 后，需要重新索引旧文档。

### provider/model 不匹配是什么意思？

当前 `.env` 中的 embedding 配置，与旧 index artifact 记录的 metadata 不一致。PureLink 会拒绝混合向量空间，并提示你执行知识库级 `reindex`。

### `sentence_transformers` 为什么报未安装？

`sentence_transformers` 现在是高级可选方案，不进入默认安装。

如需启用：

```bash
python -m pip install -r requirements-embedding-torch.txt
```

如果未安装就配置：

```env
EMBEDDING_PROVIDER=sentence_transformers
```

系统会返回 `EMBEDDING_PROVIDER_NOT_INSTALLED`。

## PDF 与文本处理

### 普通 PDF 可以处理，扫描 PDF 为什么失败？

Core 版本只支持**普通文本型 PDF**。扫描件、图片式 PDF 默认不走 OCR fallback。

常见表现：

- `PDF_TEXT_GARBLED`
- `PDF_TEXT_EXTRACTION_FAILED`
- `TEXT_QUALITY_TOO_LOW`

如果你需要扫描 PDF OCR，需要后续接入 OCR 扩展，而不是依赖当前默认部署。

### 文件内容质量过低是什么意思？

PureLink 在 chunk 入库前会做文本清洗和质量检测。以下情况会被拒绝：

- 空文本
- 乱码文本
- 二进制样式文本
- 含明显控制字符的文本

这样可以避免低质量内容进入 `DocumentChunk` 和索引。

### 为什么 ask 没有直接给答案？

当前 Core 版本会先判断检索结果是否足够可靠。如果没有检索到结果，或者最高分低于 `RETRIEVAL_MIN_SCORE`，系统会返回：

```text
当前知识库中没有找到足够可靠的依据，无法确认该问题。
```

这表示系统在避免强行编造答案。你可以：

- 换一个更具体的问题
- 上传更相关的文档
- 调低 `RETRIEVAL_MIN_SCORE`

## OCR / ASR / 多模态

### 为什么 `make check` 里 OCR / ASR 显示 disabled？

这是当前 Core 版本的默认行为，不是故障。

默认配置：

```env
ENABLE_OCR=false
OCR_PROVIDER=disabled

ENABLE_MEDIA=false
ASR_PROVIDER=disabled

MULTIMODAL_PROVIDER=disabled
```

### 上传 `.png`、`.jpg`、`.mp3`、`.mp4` 为什么被拒绝？

因为当前 Core 版本专注文本类知识库。这些类型会返回：

- `UNSUPPORTED_FILE_TYPE`
- 或 `FEATURE_NOT_ENABLED`

## Provider Status 接口

Provider 状态接口：

```http
GET /api/v1/system/providers
```

返回中不会包含 API key 或 secret，只会显示：

- provider 名称
- 是否配置完成
- 是否需要 API key
- 当前 mode
- 提示信息

## 镜像和缓存体积

查看镜像体积：

```bash
docker images
docker history --human purelink-api
docker history --human purelink-worker
```

清理 Docker build cache：

```bash
docker builder prune -af
```

模型缓存默认落在宿主机 `./models`，不会写进 Git，也不会被复制进默认镜像。

## 常见命令

```bash
docker compose ps
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f redis
docker compose exec redis redis-cli ping
make check
```
