# PureLink 常用开发命令

这份文档收集 PureLink 日常开发里最常用的命令，重点覆盖：

- 启动数据库 / 后端 / 前端
- 查看 Docker 和日志
- 查看 PostgreSQL 里的表和数据
- 执行迁移
- 运行测试
- 验证 worker 和 E2E

默认项目根目录：

```bash
cd /home/pmk/projects/purelink
```

## 1. 数据库

### 启动数据库容器

```bash
cd /home/pmk/projects/purelink
docker compose up -d db
```

### 查看数据库容器状态

```bash
cd /home/pmk/projects/purelink
docker compose ps
```

### 查看数据库日志

```bash
cd /home/pmk/projects/purelink
docker compose logs -f db
```

### 进入 PostgreSQL

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink
```

进入 `psql` 后常用命令：

```sql
\dt
\d users
\d knowledge_bases
\d documents
\d conversations
\d messages
\d document_tasks
SELECT * FROM alembic_version;
SELECT id, email, username FROM users ORDER BY id DESC LIMIT 20;
SELECT id, name, scope, owner_id, team_id FROM knowledge_bases ORDER BY id DESC LIMIT 20;
SELECT id, original_filename, review_status, processing_status FROM documents ORDER BY id DESC LIMIT 20;
SELECT id, document_id, task_type, status, retry_count FROM document_tasks ORDER BY id DESC LIMIT 20;
\q
```

### 不进入 psql，直接执行单条 SQL

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink -c "\dt"
```

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink -c "SELECT id, email, username FROM users ORDER BY id DESC LIMIT 10;"
```

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink -c "SELECT id, original_filename, review_status, processing_status FROM documents ORDER BY id DESC LIMIT 10;"
```

### 用 VS Code 图形化查看数据库

当前推荐使用 VS Code 的 `SQLTools` + PostgreSQL 驱动。

已安装扩展：

- `mtxr.sqltools`
- `mtxr.sqltools-driver-pg`

以后查看数据库时，按下面做：

1. 在 VS Code 里按 `Ctrl+Shift+P`
2. 执行 `SQLTools: Show Connections`
3. 如果还没有连接，执行 `SQLTools: Add New Connection`
4. 按下面参数创建连接：

```text
Connection Name: PureLink Local
Database Type: PostgreSQL
Server/Host: 127.0.0.1
Port: 5432
Database: purelink
Username: purelink
Password: purelink
Use SSL: No
```

连接成功后，你可以：

- 展开 schema 看表结构
- 右键表查看数据
- 新建 `.session.sql` 文件直接跑 SQL

如果连接失败，先确保数据库容器在运行：

```bash
cd /home/pmk/projects/purelink
docker compose up -d db
docker compose ps
```

然后再试图形化连接。

## 2. 后端

### 本地启动后端

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

### 先执行迁移，再启动后端

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
alembic upgrade head
python -m uvicorn app.main:app --reload
```

### 健康检查

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### 打开 API 文档

```text
http://127.0.0.1:8000/docs
```

### 用更详细的 SQL 日志启动后端

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
DB_ECHO=true python -m uvicorn app.main:app --reload
```

## 3. 前端

### 安装并启动前端

```bash
cd /home/pmk/projects/purelink/frontend
cp .env.example .env.local
npm install
npm run dev
```

### 前端地址

```text
http://127.0.0.1:3000
```

### 检查前端环境变量

```bash
cd /home/pmk/projects/purelink/frontend
cat .env.local
```

应至少包含：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## 4. Docker 全栈

### 启动后端整套服务

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
docker compose up --build -d
```

### 查看全部服务状态

```bash
cd /home/pmk/projects/purelink
docker compose ps
```

### 查看 API / DB / worker 日志

```bash
cd /home/pmk/projects/purelink
docker compose logs -f db api worker
```

### 停止全部服务

```bash
cd /home/pmk/projects/purelink
docker compose down
```

## 5. Alembic 迁移

### 升级到最新版本

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
alembic upgrade head
```

### 回滚一个版本

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
alembic downgrade -1
```

### 查看当前迁移版本

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
alembic current
```

### 查看迁移历史

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
alembic history
```

## 6. 测试

### 跑 Python + Go 测试

```bash
cd /home/pmk/projects/purelink
make test
```

### 只跑 Python 测试

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m pytest
```

### 只跑一个测试文件

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m pytest tests/test_documents.py
```

### 只跑一个关键测试

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m pytest tests/test_documents.py -k "personal_ask_creates_and_reuses_conversation_history"
```

### 跑 Go worker 测试

```bash
cd /home/pmk/projects/purelink/worker-go
go test ./...
```

## 7. Smoke / E2E

### 最小冒烟

```bash
cd /home/pmk/projects/purelink
make smoke
```

### 完整 E2E

```bash
cd /home/pmk/projects/purelink
make e2e
```

### 跑完后保留容器，方便继续调试

```bash
cd /home/pmk/projects/purelink
KEEP_STACK_UP=1 make smoke
KEEP_STACK_UP=1 make e2e
```

### 单独跑某个 E2E 脚本

```bash
cd /home/pmk/projects/purelink
scripts/e2e/01_personal_flow.sh
scripts/e2e/02_team_review_flow.sh
scripts/e2e/03_permissions_flow.sh
scripts/e2e/04_worker_flow.sh
```

## 8. Experimental Go worker

`worker-go` is retained as an experimental/early implementation. The supported Docker Compose runtime uses the Python processing worker, and the Go worker is not feature-equivalent to that path. See [Docker Deployment](docker-deployment.md#python-and-go-worker-positioning) before running it.

### 本地启动 Go worker

```bash
cd /home/pmk/projects/purelink
go run ./worker-go/cmd/parse-worker
```

### 编译 worker

```bash
cd /home/pmk/projects/purelink/worker-go
go build ./cmd/parse-worker
```

## 9. 常见调试命令

### 查看 8000 / 3000 端口是否被占用

```bash
ss -ltn | grep 8000 || true
ss -ltn | grep 3000 || true
```

### 查看最近创建的用户

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink -c "SELECT id, email, username, created_at FROM users ORDER BY id DESC LIMIT 20;"
```

### 查看最近上传的文档

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink -c "SELECT id, original_filename, review_status, processing_status, created_at FROM documents ORDER BY id DESC LIMIT 20;"
```

### 查看最近的处理任务

```bash
cd /home/pmk/projects/purelink
docker compose exec db psql -U purelink -d purelink -c "SELECT id, document_id, task_type, status, retry_count, error_message FROM document_tasks ORDER BY id DESC LIMIT 20;"
```

### 查看本地产物目录

```bash
cd /home/pmk/projects/purelink
ls -la data/uploads
ls -la data/parsed
ls -la data/chunks
ls -la data/vector_store
```

## 10. Git / GitHub

### 先看当前改了什么

```bash
cd /home/pmk/projects/purelink
git status --short
```

### 看当前分支

```bash
cd /home/pmk/projects/purelink
git branch --show-current
```

### 看远程仓库地址

```bash
cd /home/pmk/projects/purelink
git remote -v
```

### 提交今天更新的文档

如果你这次只想提交文档，执行：

```bash
cd /home/pmk/projects/purelink
git add DEV_COMMANDS.md DEVELOPMENT_LOG.md README.md PLAN.md test.md
git commit -m "docs: update development docs and daily commands"
git push origin main
```

### 提交今天所有准备一起推送的改动

如果你要把今天这轮前后端、测试、文档一起推上去，先检查状态，再有选择地加入：

```bash
cd /home/pmk/projects/purelink
git status --short
```

按当前仓库状态，常见会包括：

- `.gitignore`
- `DEV_COMMANDS.md`
- `DEVELOPMENT_LOG.md`
- `README.md`
- `PLAN.md`
- `test.md`
- `frontend/`
- `app/services/...`
- `app/api/v1/...`
- `tests/test_documents.py`

可以这样加入：

```bash
cd /home/pmk/projects/purelink
git add .gitignore DEV_COMMANDS.md DEVELOPMENT_LOG.md README.md PLAN.md test.md frontend app tests
git commit -m "feat: finalize frontend integration and developer workflow"
git push origin main
```

说明：

- `frontend/node_modules/`、`frontend/.next/`、`.env`、运行产物等内容已经在 `.gitignore` 里，不会被一起提交
- `git add frontend` 会把前端源码纳入版本控制，但不会把 `node_modules` 带进去

### 提交前再看一眼 diff

```bash
cd /home/pmk/projects/purelink
git diff --staged
```

### 查看最近提交

```bash
cd /home/pmk/projects/purelink
git log --oneline --decorate -n 10
```

### 第一次推送主分支时使用

如果是第一次推这个本地分支，可以执行：

```bash
cd /home/pmk/projects/purelink
git push -u origin main
```
