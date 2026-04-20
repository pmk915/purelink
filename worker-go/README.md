# Go Document Worker

`worker-go/` 是 PureLink 当前阶段的最小 Go worker 目录。

当前 worker 已支持四类任务：

- `task_type = parse`
- `task_type = chunk`
- `task_type = embed`
- `task_type = index`
- `status = pending`

worker 抢到任务后会先根据 `task_type` 分发处理：

### parse

1. 把任务状态改为 `processing`
2. 写入 `started_at`
3. 读取 `documents.storage_path` 指向的源文件
4. 解析 `.txt` 和 `.md`
5. 按当前 Python 解析规则把结果写到 `data/parsed`
6. 成功时把任务改为 `succeeded`，并把文档 `processing_status` 改为 `parsed`
7. 失败时把任务改为 `failed`，写入 `error_message`，递增 `retry_count`，并把文档 `processing_status` 改为 `failed`

### chunk

1. 把任务状态改为 `processing`
2. 写入 `started_at`
3. 读取对应的 parsed JSON
4. 按当前 Python `document_chunker.py` 规则切分文本
5. 把结果写到 `data/chunks`
6. 成功时把任务改为 `succeeded`
7. 失败时把任务改为 `failed`，写入 `error_message`，递增 `retry_count`

chunk 任务本身不会额外修改 `document.processing_status`，这样可以保持和当前 Python 同步 chunk 接口的行为一致。

### embed / index

1. 把任务状态改为 `processing`
2. 写入 `started_at`
3. 读取对应的 chunk JSON
4. 按当前 Python `document_embedding.py` 的 `hashed_bow_v1` 规则生成向量
5. 把结果写到 `${VECTOR_STORE_DIR}` 下兼容 Python retrieval 的 `index.json`
6. 成功时把任务改为 `succeeded`，并把文档 `processing_status` 改为 `indexed`
7. 失败时把任务改为 `failed`，写入 `error_message`，递增 `retry_count`，并把文档 `processing_status` 改为 `failed`

当前阶段 `embed` 和 `index` 都会落到同一份本地索引文件，这是为了保持和当前 Python 同步 embedding / index 能力兼容。

## 目录结构

```text
worker-go/
├── cmd/
│   └── parse-worker/
│       └── main.go
├── internal/
│   ├── chunker/
│   │   ├── chunker.go
│   │   └── chunker_test.go
│   ├── config/
│   │   └── config.go
│   ├── embedder/
│   │   ├── embedder.go
│   │   └── embedder_test.go
│   ├── parser/
│   │   └── parser.go
│   └── tasks/
│       └── worker.go
└── go.mod
```

## 环境要求

- Go 1.21+
- PostgreSQL

当前 worker 只支持 PostgreSQL，因为任务领取依赖 `FOR UPDATE SKIP LOCKED`。

## 启动方式

建议从项目根目录启动，这样 `UPLOAD_DIR=data/uploads`、`PARSED_DIR=data/parsed`、`CHUNK_DIR=data/chunks` 和 `VECTOR_STORE_DIR=data/vector_store` 会和 Python 服务保持一致：

```bash
cd /home/pmk/projects/purelink
go run ./worker-go/cmd/parse-worker
```

本地编译验证：

```bash
cd /home/pmk/projects/purelink/worker-go
go test ./...
go build ./cmd/parse-worker
```

如果你已经使用项目根目录的 `docker-compose.yml`，通常不需要单独手动起 worker。Compose 会自动构建 `worker-go/Dockerfile` 并和 `db`、`api` 一起启动。

worker 会自动读取项目根目录的 `.env`。如果环境变量已经在 shell 中设置，则优先使用 shell 中的值。

可选环境变量：

- `PURELINK_BASE_DIR`：项目根目录，默认是当前工作目录
- `PURELINK_ENV_FILE`：自定义 `.env` 路径
- `WORKER_POLL_INTERVAL`：轮询间隔，默认 `5s`
- `VECTOR_STORE_DIR`：本地向量索引目录，默认 `data/vector_store`

## 从零验证

1. 启动 PostgreSQL，并确认 `.env` 中的 `DATABASE_URL` 指向可用库
2. 运行 `alembic upgrade head`
3. 启动 FastAPI 服务
4. 上传一个可解析文档，并创建一个 `parse`、`chunk`、`embed` 或 `index` 任务
5. 启动 Go worker
6. 轮询任务状态，确认它从 `pending -> processing -> succeeded`
7. 如果是 parse 任务，检查 `data/parsed` 下是否生成了解析结果
8. 如果是 chunk 任务，检查 `data/chunks` 下是否生成了 chunk 结果
9. 如果是 embed / index 任务，检查 `data/vector_store` 下是否生成或更新了 `index.json`

如果同一个文档已经有一个 `pending` 或 `processing` 的同类型任务，再次创建同类型任务应该直接返回 `409`，不会创建第二个活跃任务。

个人知识库示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents/<document_id>/parse-tasks \
  -H "Authorization: Bearer <access_token>"
```

查询任务状态：

```bash
curl http://127.0.0.1:8000/api/v1/document-tasks/<task_id> \
  -H "Authorization: Bearer <access_token>"
```

如果任务成功，应该看到：

### parse 验证结果

- `task.status = succeeded`
- `document.processing_status = parsed`
- `data/parsed/personal/.../document_<document_id>.json` 或 `data/parsed/team/.../document_<document_id>.json` 已生成

### chunk 验证示例

先保证对应文档已经 parse 成功，再创建 chunk 任务：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents/<document_id>/chunk-tasks \
  -H "Authorization: Bearer <access_token>"
```

如果 chunk 任务成功，应该看到：

- `task.status = succeeded`
- 文档通常仍保持 `processing_status = parsed`
- `data/chunks/personal/.../document_<document_id>.json` 或 `data/chunks/team/.../document_<document_id>.json` 已生成

### embed / index 验证示例

先保证对应文档已经 chunk 成功，再创建 embed 或 index 任务：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents/<document_id>/embed-tasks \
  -H "Authorization: Bearer <access_token>"
```

或：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents/<document_id>/index-tasks \
  -H "Authorization: Bearer <access_token>"
```

如果 embed / index 任务成功，应该看到：

- `task.status = succeeded`
- `document.processing_status = indexed`
- `data/vector_store/personal/.../index.json` 或 `data/vector_store/team/.../index.json` 已生成或更新
