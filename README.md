# PureLink

PureLink 是一个面向团队内部文档管理的 AI 知识库问答与任务助手平台。

当前技术路线预期如下：

- 后端：FastAPI
- 数据库：PostgreSQL 或 MySQL
- 缓存：Redis
- AI：Embedding + 向量库 + RAG
- 部署：Docker

当前仓库阶段聚焦后端底座、认证、个人知识库、团队协作基础能力、团队知识库权限边界、最小文档上传闭环、团队审核流、最小文档解析闭环、统一文档任务机制、最小 Go parse/chunk/embed/index worker、chunk 检索准备层和最小 embedding/retrieval 层，不展开完整问答、RAG 编排和复杂任务系统实现。

## 当前阶段目标

当前目标是建立一个可持续扩展的 FastAPI 后端底座，并已经进入多用户协作前置阶段，当前重点包括：

- 服务可以本地启动
- 提供基础健康检查与认证接口
- 数据库底座、核心实体与迁移基线清晰可扩展
- 个人知识库能力可用
- 团队创建、邀请码与入队流程可用
- 团队知识库权限控制可用
- 文档上传与提交记录可用
- 团队文档审核流可用
- txt / md 文档解析最小闭环可用
- 文档解析任务机制可用
- Go parse/chunk/embed/index worker 最小实现可用
- parsed text -> chunk 检索准备层可用
- chunk -> embedding -> retrieval 最小闭环可用
- 目录职责清晰，便于继续扩展文档上传和审核流

## 当前已实现能力

- FastAPI 应用入口、配置、日志、异常处理
- PostgreSQL / SQLAlchemy / Alembic 基础接线
- 用户注册、登录、当前用户查询
- 个人知识库 CRUD
- 团队创建、团队列表、团队详情
- 管理员生成邀请码、查看邀请码
- 用户通过邀请码加入团队
- 团队成员列表
- 团队知识库 CRUD 与成员/管理员权限区分
- 个人知识库文档上传与列表
- 团队知识库文档提交与列表
- 团队待审核文档列表、审核通过与拒绝
- 个人文档与已审核团队文档的最小解析接口
- 解析任务创建与任务状态查询
- Go worker 可轮询 `pending parse` / `pending chunk` / `pending embed` / `pending index` 任务并推进状态
- 个人与团队文档的最小 chunk 接口
- 个人与团队知识库的最小 embedding / retrieval 接口

## 当前目录结构

```text
purelink/
├── app/
│   ├── api/
│   │   ├── deps.py     # API 可复用依赖
│   │   ├── router.py   # 总路由注册入口
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── document_tasks.py
│   │       ├── knowledge_bases.py
│   │       ├── team_document_reviews.py
│   │       ├── team_invites.py
│   │       ├── team_knowledge_bases.py
│   │       ├── teams.py
│   │       ├── system.py
│   │       └── users.py
│   ├── core/
│   │   ├── application.py
│   │   ├── config.py   # 环境变量与应用配置读取
│   │   ├── exceptions.py
│   │   ├── logging.py  # 基础日志配置
│   │   └── security.py # 密码哈希与 token 工具
│   ├── db/
│   │   ├── base.py     # SQLAlchemy Base 与 metadata
│   │   └── session.py  # engine 与 Session 工厂
│   ├── models/
│   │   ├── conversation.py
│   │   ├── document.py
│   │   ├── document_task.py
│   │   ├── knowledge_base.py
│   │   ├── message.py
│   │   ├── team.py
│   │   └── user.py
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── document.py
│   │   ├── document_task.py
│   │   ├── knowledge_base.py
│   │   ├── team.py
│   │   └── user.py
│   ├── services/
│   │   ├── auth.py
│   │   ├── document_chunker.py
│   │   ├── document.py
│   │   ├── document_embedding.py
│   │   ├── document_task.py
│   │   ├── document_parser.py
│   │   ├── knowledge_base.py
│   │   └── team.py
│   └── main.py         # 应用入口，仅创建 app
├── alembic/
│   ├── env.py
│   └── versions/       # 数据库迁移版本，当前包含 document_tasks 表迁移
├── alembic.ini         # Alembic 配置
├── data/
│   ├── chunks/         # 本地 chunk 结果目录
│   ├── uploads/        # 本地上传文件预留目录
│   ├── parsed/         # 本地解析结果目录
│   └── vector_store/   # 本地向量数据预留目录
├── docs/               # 设计文档与补充说明
│   └── team_domain_model.md
├── logs/               # 本地日志目录
├── scripts/            # 开发辅助脚本目录
│   ├── e2e/            # Bash E2E 测试脚本
│   └── verify_db.py    # 数据库连接与建表验证脚本
├── tests/
│   ├── fixtures/       # E2E 与上传测试固定样例文件
│   ├── test_auth.py    # 注册、登录、当前用户测试
│   ├── test_documents.py # 文档上传与列表测试
│   ├── test_knowledge_bases.py # 知识库 CRUD 测试
│   ├── test_team_knowledge_bases.py # 团队知识库 CRUD 测试
│   ├── test_teams.py   # 团队创建、邀请、入队测试
│   ├── test_team_models.py # 团队域模型最小测试
│   └── test_health.py  # 健康检查最小测试
├── AGENTS.md           # 仓库内协作约束
├── .dockerignore       # Docker 构建上下文过滤
├── Dockerfile          # FastAPI 服务镜像定义
├── Makefile            # 一键启动与日志查看命令
├── PLAN.md             # 第一阶段计划与里程碑
├── docker-compose.yml  # FastAPI / PostgreSQL / Go worker 编排
├── README.md
├── requirements.txt
└── worker-go/          # 最小 Go parse/chunk/embed/index worker
    └── Dockerfile      # Go worker 镜像定义
```

## 当前可运行目标

当前仓库不是完整业务系统，而是一个最小后端骨架。现阶段启动目标如下：

- 启动 FastAPI 服务
- 访问版本化 API 根路由确认服务信息
- 访问健康检查接口确认服务可用

示例接口：

- `GET /api/v1/`
- `GET /api/v1/health`

## 从零启动项目

推荐优先使用 Docker Compose 跑通完整链路。这样可以一次性拉起：

- FastAPI 主服务
- PostgreSQL
- Go document worker

### 方式一：Docker Compose 一键启动

前置要求：

- Docker Engine / Docker Desktop
- Docker Compose v2

首次启动：

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
make up
```

如果你不想用 `make`，直接执行：

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
docker compose up --build -d
```

查看状态：

```bash
make ps
docker compose logs -f api worker
```

启动成功后：

- API 文档：`http://127.0.0.1:8000/docs`
- API 健康检查：`http://127.0.0.1:8000/api/v1/health`
- PostgreSQL：`127.0.0.1:5432`

容器编排行为：

- `db` 使用 `postgres:16-alpine`
- `api` 启动前会自动执行 `alembic upgrade head`
- `worker` 会在 `db` 和 `api` 都就绪后启动
- `data/` 和 `logs/` 会挂载到容器内，便于直接查看解析、chunk 和索引结果

停止服务：

```bash
make down
```

### 方式二：本地启动（不使用 Docker）

建议在 WSL2 Ubuntu 环境中开发。

1. 进入项目目录
2. 创建并激活虚拟环境
3. 安装依赖
4. 准备环境变量文件
5. 启动服务

```bash
cd /home/pmk/projects/purelink
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

启动后可访问：

- `http://127.0.0.1:8000/api/v1/`
- `http://127.0.0.1:8000/api/v1/health`
- `http://127.0.0.1:8000/docs`

## 一键启动后的最小验证

如果你想验证“服务、数据库、worker、文档处理链”都通了，最短路径如下：

1. 访问 `GET /api/v1/health`，确认 API 正常
2. 在 `http://127.0.0.1:8000/docs` 注册并登录，拿到 token
3. 创建一个个人知识库
4. 上传一个 `.txt` 或 `.md` 文档
5. 依次创建 `parse-task`、`chunk-task`、`embed-task`
6. 查询 `GET /api/v1/document-tasks/{task_id}`，确认任务变成 `succeeded`
7. 调用 retrieval 或 ask 接口，确认能返回结果

如果你要直接看中间产物，可以检查：

- `data/uploads/`
- `data/parsed/`
- `data/chunks/`
- `data/vector_store/`

## 环境变量

应用启动时会优先读取项目根目录下的 `.env` 文件；如果某个变量未设置，则使用代码中的默认值。

推荐先复制模板文件：

```bash
cp .env.example .env
```

当前预留的最小环境变量包括：

- `APP_NAME`：应用名称
- `APP_ENV`：运行环境，例如 `development`
- `APP_DEBUG`：是否开启调试
- `APP_VERSION`：应用版本号
- `LOG_LEVEL`：日志级别
- `AUTH_SECRET_KEY`：JWT 签名密钥，本地开发可用默认值，生产环境必须更换
- `AUTH_ALGORITHM`：当前 token 算法，默认 `HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES`：访问 token 过期时间，单位分钟
- `DATABASE_URL`：SQLAlchemy 使用的数据库连接串
- `DB_ECHO`：是否打印 SQLAlchemy SQL 日志
- `CORS_ALLOW_ORIGINS`：允许跨域来源，逗号分隔
- `CORS_ALLOW_METHODS`：允许的跨域方法，逗号分隔
- `CORS_ALLOW_HEADERS`：允许的跨域请求头，逗号分隔
- `CORS_ALLOW_CREDENTIALS`：是否允许跨域携带凭证
- `UPLOAD_DIR`：文档上传目录，默认 `data/uploads`
- `PARSED_DIR`：文档解析结果目录，默认 `data/parsed`
- `CHUNK_DIR`：文档 chunk 结果目录，默认 `data/chunks`
- `VECTOR_STORE_DIR`：本地向量索引目录，默认 `data/vector_store`
- `LLM_PROVIDER`：问答生成器类型，当前支持 `heuristic` 和 `openai_compatible`
- `LLM_API_BASE`：真实 LLM 的 API 基地址
- `LLM_API_KEY`：真实 LLM 的 API key
- `LLM_MODEL`：真实 LLM 使用的模型名
- `POSTGRES_DB`：Docker Compose 默认数据库名
- `POSTGRES_USER`：Docker Compose 默认数据库用户
- `POSTGRES_PASSWORD`：Docker Compose 默认数据库密码
- `POSTGRES_PORT`：Docker Compose 暴露到宿主机的数据库端口
- `APP_PORT`：Docker Compose 暴露到宿主机的 API 端口
- `WORKER_POLL_INTERVAL`：Go worker 轮询数据库任务的时间间隔

## 常见问题排查

1. `docker compose up` 失败，提示端口冲突
   `8000` 或 `5432` 已被占用，修改 `.env` 里的 `APP_PORT` 或 `POSTGRES_PORT` 后重试。

2. `api` 容器一直不健康
   先看 `docker compose logs api`。常见原因是 `DATABASE_URL` 不可用，或者 Alembic 迁移执行失败。

3. `worker` 已启动，但任务一直停在 `pending`
   先看 `docker compose logs worker`。再检查文档是否满足准入条件：
   `parse` 需要可解析源文件；
   `chunk` 需要 parsed 结果；
   `embed/index` 需要 chunk 结果；
   团队文档还必须已经 `approved`。

4. `data/` 或 `logs/` 出现权限问题
   这是 bind mount 常见问题。WSL/Linux 下可执行：
   `sudo chown -R $USER:$USER data logs`

5. 真实 LLM 调用失败
   本地冒烟验证先保持 `LLM_PROVIDER=heuristic`。
   如果切到 `openai_compatible`，必须同时配置 `LLM_API_BASE`、`LLM_API_KEY` 和 `LLM_MODEL`。

6. PostgreSQL 容器起来了，但 API 仍然连不上
   确认不是沿用了宿主机的 `localhost` 连接串。Compose 场景下服务间连接统一走 `db:5432`，当前 `docker-compose.yml` 已经为 `api` 和 `worker` 显式覆盖了 `DATABASE_URL`。

## E2E Test Scripts

当前仓库已经补了一套可以直接落地的 Bash E2E 脚本，目录在 `scripts/e2e/`：

- `01_personal_flow.sh`：覆盖个人知识库从上传到 ask 的完整链路
- `02_team_review_flow.sh`：覆盖团队邀请、入队、上传、审核、检索和 ask
- `03_permissions_flow.sh`：覆盖管理员、成员、非成员的权限边界
- `04_worker_flow.sh`：覆盖 worker 执行和中间产物落盘
- `run_all.sh`：顺序执行全部场景

运行全部 E2E：

```bash
cd /home/pmk/projects/purelink
scripts/e2e/run_all.sh
```

运行单个场景：

```bash
cd /home/pmk/projects/purelink
scripts/e2e/01_personal_flow.sh
scripts/e2e/02_team_review_flow.sh
scripts/e2e/03_permissions_flow.sh
scripts/e2e/04_worker_flow.sh
```

脚本依赖尽量收敛到：

- `bash`
- `curl`
- `python3`

默认假设：

- API 已启动
- worker 正在运行
- `.env` 已配置完成
- 数据库迁移已执行

## CI

当前仓库已经补了两条 GitHub Actions workflow：

- `ci`：快速 CI，只跑 Python 测试和 Go 测试
- `smoke`：最小 smoke CI，使用 Docker Compose 拉起 `db / api / worker`，并执行 `scripts/e2e/01_personal_flow.sh`

对应文件：

- `.github/workflows/ci.yml`
- `.github/workflows/smoke.yml`

本地建议的对应验证命令：

```bash
cd /home/pmk/projects/purelink
make test
make smoke
make e2e
```

说明：

- `make test`：运行 `pytest` 和 `go test`
- `make smoke`：拉起 Compose 环境并跑最小个人知识库链路
- `make e2e`：拉起 Compose 环境并跑全部 Bash E2E 脚本

GitHub 上的触发方式：

- `ci`：`push` 到 `main/master` 或 `pull_request`
- `smoke`：`workflow_dispatch`，以及 `push` 到 `main/master`

## 数据库底座

当前项目已补齐同步 SQLAlchemy 2.0、PostgreSQL 驱动和 Alembic 基础结构，核心实体包括：

- `User`：平台用户
- `KnowledgeBase`：知识库
- `Document`：知识库下的文档文件
- `Conversation`：用户与知识库关联的问答会话
- `Message`：会话中的消息记录

模型关系概要：

- 一个 `User` 可以拥有多个 `KnowledgeBase`
- 一个 `User` 可以上传多个 `Document`
- 一个 `User` 可以发起多个 `Conversation`
- 一个 `KnowledgeBase` 可以包含多个 `Document`
- 一个 `KnowledgeBase` 可以关联多个 `Conversation`
- 一个 `Conversation` 可以包含多条 `Message`

### 数据库初始化

1. 确保本地 PostgreSQL 已启动
2. 创建 `purelink` 用户和数据库
3. 复制 `.env.example` 为 `.env`
4. 执行 Alembic 迁移
5. 运行数据库验证脚本

推荐在 Ubuntu / WSL2 下执行：

```bash
sudo apt update
sudo apt install -y postgresql postgresql-client
sudo service postgresql start
sudo service postgresql status

sudo -u postgres psql -c "CREATE USER purelink WITH PASSWORD 'purelink';"
sudo -u postgres psql -c "CREATE DATABASE purelink OWNER purelink;"
```

停止本地 PostgreSQL：

```bash
sudo service postgresql stop
```

### 执行迁移

完成依赖安装并准备好 `.env` 后，在项目根目录执行：

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
cp .env.example .env
alembic upgrade head
```

当前会执行到最新版本，包括团队域模型迁移 `20260420_0002`。

查看当前迁移版本：

```bash
alembic current
```

回滚一个版本：

```bash
alembic downgrade -1
```

重新升到最新版本：

```bash
alembic upgrade head
```

后续新增模型变更时，可生成新迁移：

```bash
alembic revision --autogenerate -m "describe change"
```

当前首版迁移会创建以下表：

- `users`
- `knowledge_bases`
- `documents`
- `conversations`
- `messages`

## 团队协作域模型基础

Milestone M4.5 已完成团队协作的数据库域模型准备，Milestone M4.6 已补上第一组团队接口：团队创建、团队列表、团队详情、邀请码生成与列表、邀请码入队、成员列表。

新增实体：

- `Team`：团队主体，表示一个协作空间
- `TeamMember`：团队成员关系，记录成员角色和状态
- `TeamInvite`：团队邀请码与使用状态

扩展后的核心模型：

- `KnowledgeBase`：
  - 新增 `scope`，取值为 `personal` 或 `team`
  - 新增 `team_id`
  - 约束规则是：`personal` 必须有 `owner_id` 且 `team_id` 为空；`team` 必须有 `team_id` 且 `owner_id` 为空
- `Document`：
  - 原 `status` 已拆分为 `review_status` 和 `processing_status`
  - 新增 `submitted_by`、`reviewed_by`、`reviewed_at`、`review_comment`
  - 个人知识库文档后续应使用 `review_status=not_required`
  - 团队知识库文档后续可进入 `pending_review -> approved/rejected` 流程

当前新增的数据表包括：

- `teams`
- `team_members`
- `team_invites`

更完整的字段和关系说明见 `docs/team_domain_model.md`。

### 为什么旧的个人知识库逻辑仍然有效

旧的个人知识库 CRUD 没有被团队逻辑替换，而是被“限定为 personal scope”：

- 当前个人知识库创建逻辑仍然只写入 `scope=personal`
- 个人知识库列表、详情、更新、删除仍然只按 `owner_id=current_user.id` 查询
- 现有 `/api/v1/knowledge-bases` 接口不会暴露团队知识库
- 已有个人知识库测试仍然通过，说明现有行为未回归

这意味着团队协作能力是叠加在现有底座上的，而不是通过重写个人知识库逻辑来实现。

## 团队接口

当前已提供最小团队协作入口，所有接口都要求登录：

- `POST /api/v1/teams`
- `GET /api/v1/teams`
- `GET /api/v1/teams/{team_id}`
- `POST /api/v1/teams/{team_id}/invites`
- `GET /api/v1/teams/{team_id}/invites`
- `POST /api/v1/team-invites/join`
- `GET /api/v1/teams/{team_id}/members`

规则概要：

- 创建团队后，当前用户会自动成为该团队的 `admin`
- 团队详情和成员列表只有团队成员可访问
- 生成邀请码和查看邀请码列表只有团队 `admin` 可操作
- 邀请码加入会校验状态、过期时间和重复加入

### 创建团队

请求体示例：

```json
{
  "name": "Platform Team",
  "description": "Core collaboration team"
}
```

返回字段：

- `id`
- `name`
- `description`
- `created_by`
- `created_at`
- `updated_at`
- `my_role`
- `my_status`

### 生成邀请码

请求体示例：

```json
{
  "expires_in_days": 7
}
```

返回字段：

- `id`
- `team_id`
- `code`
- `invited_by`
- `expires_at`
- `used_by`
- `used_at`
- `status`
- `created_at`
- `updated_at`

### 通过邀请码加入团队

请求体示例：

```json
{
  "code": "generated-invite-code"
}
```

成功后返回团队信息，并带上当前用户在该团队中的 `my_role` 和 `my_status`。

### 成员列表

成员列表返回团队成员关系和最小用户信息，包括：

- `id`
- `team_id`
- `user_id`
- `role`
- `status`
- `joined_at`
- `created_at`
- `updated_at`
- `user.id`
- `user.email`
- `user.username`

### 本地验证团队创建、邀请、入队和权限差异

1. 注册并登录 Alice，拿到 `alice_token`
2. 注册并登录 Bob，拿到 `bob_token`
3. 用 Alice 创建团队
4. 用 Alice 为该团队生成邀请码
5. 用 Bob 通过邀请码加入团队
6. 验证 Bob 能访问团队详情和成员列表，但不能生成邀请码

示例流程：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams \
  -H "Authorization: Bearer <alice_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Platform Team","description":"Core collaboration team"}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/invites \
  -H "Authorization: Bearer <alice_token>" \
  -H "Content-Type: application/json" \
  -d '{"expires_in_days":7}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/team-invites/join \
  -H "Authorization: Bearer <bob_token>" \
  -H "Content-Type: application/json" \
  -d '{"code":"<invite_code>"}'
```

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id> \
  -H "Authorization: Bearer <bob_token>"
```

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id>/members \
  -H "Authorization: Bearer <bob_token>"
```

Bob 作为普通成员尝试生成邀请码，应该返回 `403`：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/invites \
  -H "Authorization: Bearer <bob_token>" \
  -H "Content-Type: application/json" \
  -d '{"expires_in_days":7}'
```

## 团队知识库接口

Milestone M4.7 已补上团队知识库 CRUD。团队知识库与个人知识库是两组独立接口：

- 个人知识库接口：`/api/v1/knowledge-bases`
- 团队知识库接口：`/api/v1/teams/{team_id}/knowledge-bases`

团队知识库规则：

- 创建、更新、删除只能由团队 `admin` 操作
- 团队 `admin` 和 `member` 都可以查看列表和详情
- 非团队成员不能访问团队知识库
- 团队知识库会写入 `scope=team`
- `team_id` 只来自路径参数，不允许客户端自行决定归属

当前接口：

- `POST /api/v1/teams/{team_id}/knowledge-bases`
- `GET /api/v1/teams/{team_id}/knowledge-bases`
- `GET /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}`
- `PATCH /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}`
- `DELETE /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents`
- `GET /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents`

### 创建团队知识库

请求体示例：

```json
{
  "name": "Shared Engineering Docs",
  "description": "Docs shared by the platform team"
}
```

返回字段：

- `id`
- `name`
- `description`
- `scope`
- `owner_id`
- `team_id`
- `created_at`
- `updated_at`

其中团队知识库返回应满足：

- `scope = team`
- `owner_id = null`
- `team_id = 路径中的 team_id`

### 查看团队知识库

- 列表接口只返回当前团队下的知识库
- 详情接口要求当前用户是该团队成员

### 更新与删除团队知识库

- `PATCH` 只更新显式传入字段
- 删除成功返回 `204 No Content`
- 更新和删除都要求当前用户是该团队 `admin`

### 本地验证 admin、member、非成员 的权限差异

1. Alice 创建团队并成为 `admin`
2. Alice 生成邀请码
3. Bob 通过邀请码加入团队成为 `member`
4. Alice 创建团队知识库
5. Bob 读取团队知识库列表和详情，应返回 `200`
6. Bob 尝试创建、更新、删除团队知识库，应返回 `403`
7. Charlie 不加入团队，访问团队知识库列表或详情，应返回 `404`

示例流程：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases \
  -H "Authorization: Bearer <alice_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Shared Engineering Docs","description":"Docs shared by the platform team"}'
```

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases \
  -H "Authorization: Bearer <bob_token>"
```

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases/<knowledge_base_id> \
  -H "Authorization: Bearer <bob_token>"
```

Bob 作为普通成员尝试创建团队知识库，应该返回 `403`：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases \
  -H "Authorization: Bearer <bob_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Should Fail"}'
```

Charlie 不是团队成员，访问列表应返回 `404`：

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases \
  -H "Authorization: Bearer <charlie_token>"
```

### 团队知识库文档提交与列表

团队成员和管理员都可以向团队知识库提交文档，但提交后不会直接进入“已审核”状态。

团队文档上传规则：

- 上传接口：`POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents`
- 列表接口：`GET /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents`
- 文件保存到 `${UPLOAD_DIR}/team/team_{team_id}/knowledge_base_{knowledge_base_id}/`
- 上传时写入 `review_status = pending_review`
- 上传时写入 `processing_status = uploaded`
- 团队成员和管理员可以查看列表
- 非团队成员访问上传或列表都会返回 `404`

上传请求使用 `multipart/form-data`，字段名固定为 `file`。

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases/<knowledge_base_id>/documents \
  -H "Authorization: Bearer <member_token>" \
  -F "file=@./example.pdf"
```

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases/<knowledge_base_id>/documents \
  -H "Authorization: Bearer <admin_token>"
```

列表返回的关键字段包括：

- `id`
- `knowledge_base_id`
- `owner_id`
- `submitted_by`
- `filename`
- `original_filename`
- `file_type`
- `file_size`
- `storage_path`
- `review_status`
- `processing_status`
- `reviewed_by`
- `reviewed_at`
- `review_comment`
- `created_at`
- `updated_at`

如果团队成员刚提交一份文档，你应该看到：

- `review_status = pending_review`
- `processing_status = uploaded`
- `reviewed_by = null`
- `reviewed_at = null`

这说明文档已经记录并落盘，但还没有被审核通过，后续也不应该直接进入检索范围。

### 团队文档解析

团队文档解析接口：

- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks`

规则：

- 只有团队成员和管理员可以触发解析
- 只有 `review_status = approved` 的团队文档可以进入解析
- `pending_review` 和 `rejected` 的团队文档会返回 `409`
- 当前只支持 `.txt` 和 `.md`
- 解析成功后写入 `${PARSED_DIR}/team/team_{team_id}/knowledge_base_{knowledge_base_id}/document_{document_id}.json`
- 解析成功后更新 `processing_status = parsed`
- 解析失败后更新 `processing_status = failed`
- chunk 成功后写入 `${CHUNK_DIR}/team/team_{team_id}/knowledge_base_{knowledge_base_id}/document_{document_id}.json`
- chunk 本身不会改变 `processing_status`，文档仍保持 `parsed`

返回字段：

- `document_id`
- `knowledge_base_id`
- `processing_status`
- `parsed_path`
- `parser`
- `extracted_char_count`

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/knowledge-bases/<knowledge_base_id>/documents/<document_id>/parse \
  -H "Authorization: Bearer <member_token>"
```

如何验证未审核团队文档不能进入解析：

1. 成员上传团队文档
2. 不做审核，直接调用 parse 接口
3. 你应该收到 `409`
4. 文档在列表中的 `processing_status` 仍保持 `uploaded`
5. 管理员审核通过后，再调用 parse，才会变成 `parsed`

### 文档 Chunk 与检索准备

当前 chunk 层先走同步接口，目标是把 `parsed JSON -> chunks JSON` 这一步跑通，并为后续 embedding 预留稳定输入。

相关接口：

- 个人文档：`POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk`
- 团队文档：`POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk`

规则：

- 只有已经完成 parse 的文档才能进入 chunk
- 个人文档要求 `review_status = not_required`
- 团队文档要求 `review_status = approved`
- 团队未审核或已拒绝文档会返回 `409`
- chunk 结果写入 `${CHUNK_DIR}/personal/...` 或 `${CHUNK_DIR}/team/...`
- 当前采用简单文本切分规则：优先按空行分段，超长段落再按固定长度切分

chunk 返回字段：

- `document_id`
- `knowledge_base_id`
- `processing_status`
- `chunked_path`
- `source_parsed_path`
- `chunk_count`
- `chunk_size`

后续 embedding 的衔接方式：

1. 读取 chunk JSON 中的 `chunks`
2. 以每个 `chunk_id + text` 为单位生成 embedding
3. 把向量、chunk 文本和元数据写入向量存储
4. 检索时按 `chunk_id` 回溯到具体 chunk 内容，再用于召回和引用

### Embedding 与最小检索

当前 embedding 层使用纯本地方案，不依赖外部模型或重量级向量库：

- embedding 方案：`hashed_bow_v1`
- 向量生成方式：把 chunk 文本做分词后映射到固定维度哈希向量
- 检索方式：对 query 做同样的 embedding，然后用 cosine similarity 做 top-k 排序
- 索引存储：写入 `${VECTOR_STORE_DIR}` 下的知识库级 `index.json`

相关接口：

- 个人文档 embedding：`POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed`
- 团队文档 embedding：`POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed`
- 个人知识库检索：`POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieve`
- 团队知识库检索：`POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve`

规则：

- embedding 依赖已有 chunk 结果
- 个人文档要求 `review_status = not_required`
- 团队文档要求 `review_status = approved`
- 文档必须已经进入 `parsed` 或 `indexed` 状态
- embedding 成功后会把 `processing_status` 更新为 `indexed`
- retrieval 只会检索当前知识库下 `processing_status = indexed` 的文档

返回结果包含：

- `chunk_id`
- `document_id`
- `knowledge_base_id`
- `scope`
- `team_id`
- `text`
- `score`

本地索引路径规则：

- personal: `${VECTOR_STORE_DIR}/personal/knowledge_base_{knowledge_base_id}/index.json`
- team: `${VECTOR_STORE_DIR}/team/team_{team_id}/knowledge_base_{knowledge_base_id}/index.json`

后续问答接口的衔接方式：

1. 先调用 retrieval 接口拿到 top-k chunks
2. 把 chunk 文本和元数据作为上下文拼进 prompt
3. 交给后续问答服务生成答案
4. 如需引用展示，可直接使用返回里的 `chunk_id`、`document_id` 和文本片段

### 最小问答接口

当前问答层先实现一个最小闭环：

- 个人知识库问答：`POST /api/v1/knowledge-bases/{knowledge_base_id}/ask`
- 团队知识库问答：`POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/ask`

请求体：

```json
{
  "question": "What does PureLink store?",
  "top_k": 5
}
```

规则：

- 问答前会先执行 retrieval，拿到 top-k chunks 作为上下文
- 个人知识库只能由 owner 访问
- 团队知识库只能由 team admin / member 访问
- 团队问答只会基于 `review_status = approved` 且 `processing_status = indexed` 的文档
- 未审核、已拒绝或未完成 embedding 的团队文档不会进入问答上下文

当前实现方式：

- 问答层复用已有 retrieval service，不在接口里重复实现检索逻辑
- retrieval 结果会被拼成最小 prompt：
  1. system prompt：约束只能基于检索上下文回答
  2. user prompt：包含用户问题和检索回来的 chunk 文本
- 当前仓库支持两种 generator：
  1. `heuristic`：不调用外部 LLM，只基于检索结果生成最小 answer
  2. `openai_compatible`：通过 HTTP 调用外部 OpenAI-compatible chat completions 接口
- generator 选择通过 `LLM_PROVIDER` 控制，provider 解析放在问答服务层，不在路由里写死
- 每次 `/ask` 都会把当前问题和回答写入会话历史
- 如果请求体不传 `conversation_id`，系统会自动创建新会话
- 如果传入已有 `conversation_id`，系统会把新的问答追加到该会话

返回字段：

- `conversation_id`
- `answer`
- `citations`

`citations` 中每项至少包括：

- `chunk_id`
- `document_id`
- `knowledge_base_id`
- `scope`
- `team_id`
- `text`

返回示例：

```json
{
  "conversation_id": 7,
  "answer": "Based on the indexed knowledge base, the relevant information is: PureLink stores internal docs for teams.",
  "citations": [
    {
      "chunk_id": "12:0",
      "document_id": 12,
      "knowledge_base_id": 3,
      "scope": "personal",
      "team_id": null,
      "text": "PureLink stores internal docs for teams."
    }
  ]
}
```

本地验证步骤：

1. 上传文档并完成 `parse -> chunk -> embed`
2. 调用对应知识库的 `/ask` 接口
3. 记录返回里的 `conversation_id`
4. 检查返回里的 `answer` 和 `citations`
5. 对团队知识库，额外验证：
   - 未审核文档不会出现在 `citations`
   - 非成员访问返回 `404`
   - member 可以问答，但不能绕过审核规则

### 会话与消息持久化

当前 `/ask` 接口已经与 `Conversation` / `Message` 模型接通：

- 每次 ask 会写入两条 message：
  1. `role = user`，内容是用户问题
  2. `role = assistant`，内容是系统回答
- assistant message 会额外持久化 citations 元数据
- conversation 始终关联到具体 `knowledge_base_id`

会话相关接口：

- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`

会话创建和复用规则：

- 首次 ask 不传 `conversation_id` 时，会自动创建新会话
- 会话标题默认由第一条问题生成
- 后续 ask 传入同一个 `conversation_id` 时，会复用原会话并继续追加消息
- 不能把一个会话拿去绑定另一个知识库；这类请求会返回 `409`

消息与 citations 的存储方式：

- `user` message：只保存问题文本
- `assistant` message：保存回答文本
- `assistant` message 还会保存当前回答对应的 citations 元数据，便于后续历史页直接展示引用来源

查看历史问答的方法：

1. 调用 `/ask`，拿到 `conversation_id`
2. 调用 `GET /api/v1/conversations` 查看当前用户可访问的会话列表
3. 调用 `GET /api/v1/conversations/{conversation_id}` 查看完整消息历史

权限规则：

- 个人知识库会话：只有 owner 能查看
- 团队知识库会话：只有创建该会话的用户本人、且当前仍具备团队知识库访问权限时，才能查看
- 即使同团队其他成员有知识库访问权，也不能直接查看别人的会话历史

后续接入正式 LLM API 时，主要替换点是：

1. 保留 retrieval service 不变
2. 保留 citations 组装逻辑不变
3. 继续复用当前 `build_prompt()` 生成的 `system_prompt + user_prompt`
4. 如果外部 LLM 不是 OpenAI-compatible，只需要替换 provider 实现，不需要改 `/ask` 接口

切换到真实 LLM 的最小配置示例：

```env
LLM_PROVIDER=openai_compatible
LLM_API_BASE=https://your-llm-endpoint.example/v1
LLM_API_KEY=replace-with-real-key
LLM_MODEL=your-chat-model
```

真实 LLM 验证步骤：

1. 在 `.env` 中设置上面的 `LLM_*` 配置
2. 重启 FastAPI 服务
3. 对已完成 `parse -> chunk -> embed` 的知识库调用 `/ask`
4. 检查返回的 `answer` 是否来自真实模型
5. 检查 `citations` 是否仍然来自当前 retrieval 结果，而不是由模型自由生成

### 统一文档处理任务链

Milestone M9.1 把 `document_tasks` 扩展成统一的文档处理任务表。当前支持的 `task_type` 包括：

- `parse`
- `chunk`
- `embed`
- `index`

相关接口：

- 个人文档：
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks`
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks`
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks`
  - `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks`
- 团队文档：
  - `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks`
  - `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks`
  - `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks`
  - `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks`
- 查询任务：`GET /api/v1/document-tasks/{task_id}`

任务状态流：

- 创建时：`pending`
- 后续 worker 取走时：`processing`
- 处理成功：`succeeded`
- 处理失败：`failed`

当前统一处理链目标是：

`upload/review -> parse task -> chunk task -> embed/index task`

当前阶段已经补了最小 Go document worker。只要 worker 在运行，`pending parse`、`pending chunk`、`pending embed` 和 `pending index` 任务都会被轮询、领取并处理。

任务创建规则：

- 个人文档要求 `review_status = not_required`
- 团队文档要求 `review_status = approved`
- `parse` 任务保持当前 parse worker 逻辑
- `chunk` 任务要求文档已经完成 parse，且本地 parsed JSON 已存在
- `embed` / `index` 任务要求本地 chunk JSON 已存在
- 团队成员和管理员都可以为自己可访问的团队文档创建任务
- 非团队成员不能创建，也不能查询任务状态

任务返回字段包括：

- `id`
- `document_id`
- `task_type`
- `status`
- `error_message`
- `retry_count`
- `created_at`
- `updated_at`
- `started_at`
- `finished_at`

防重规则：

- 同一个 `document_id + task_type` 在 `pending` / `processing` 状态下只允许存在一个活跃任务
- 如果该文档已经有活跃的同类型任务，再次创建会返回 `409`
- `succeeded` / `failed` 任务不算活跃任务，后续仍然可以再次创建新任务

各任务当前的输入和输出：

1. `parse`
   - 输入：上传后的源文件
   - 输出：`${PARSED_DIR}` 下的 parsed JSON
2. `chunk`
   - 输入：parsed JSON
   - 输出：`${CHUNK_DIR}` 下的 chunk JSON
3. `embed`
   - 输入：chunk JSON
   - 输出：`${VECTOR_STORE_DIR}` 下兼容 Python retrieval 的本地索引文件
4. `index`
   - 输入：chunk 或 embedding 产物
   - 输出：`${VECTOR_STORE_DIR}` 下的可检索索引

当前 Go worker 的行为是：

1. 轮询 `document_tasks` 中 `status = pending` 且 `task_type IN ('parse', 'chunk', 'embed', 'index')` 的任务
2. 使用 PostgreSQL `FOR UPDATE SKIP LOCKED` 原子领取任务
3. 如果是 `parse`，读取源文件并写入 `data/parsed`
4. 如果是 `chunk`，读取 parsed JSON 并写入 `data/chunks`
5. 如果是 `embed` 或 `index`，读取 chunk JSON 并写入 `${VECTOR_STORE_DIR}` 下的兼容 `index.json`
6. 成功时把任务改成 `succeeded`
7. `parse` 成功后会把 `document.processing_status` 改成 `parsed`
8. `chunk` 成功后不会额外改动 `document.processing_status`
9. `embed` / `index` 成功后会把 `document.processing_status` 改成 `indexed`
10. 失败时把任务改成 `failed`，写入 `error_message`，递增 `retry_count`

后续 Go worker 的接手方式：

1. 继续复用同一张 `document_tasks` 表
2. 在 worker 侧按 `task_type` 分支处理 `parse / chunk / embed / index`
3. 当前 worker 已接手 `parse / chunk / embed / index`
4. 后续如果拆分专用 worker，只需要继续领取对应 `task_type = pending` 的任务并推进状态

启动命令：

```bash
cd /home/pmk/projects/purelink
go run ./worker-go/cmd/parse-worker
```

更详细的 worker 说明见 `worker-go/README.md`。

本地编译与运行验证：

```bash
cd /home/pmk/projects/purelink/worker-go
go test ./...
go build ./cmd/parse-worker
cd /home/pmk/projects/purelink
go run ./worker-go/cmd/parse-worker
```

### 团队文档审核接口

Milestone M5.2 已补上最小团队审核流，当前接口：

- `GET /api/v1/teams/{team_id}/review-tasks`
- `POST /api/v1/teams/{team_id}/documents/{document_id}/approve`
- `POST /api/v1/teams/{team_id}/documents/{document_id}/reject`

规则：

- 只有团队 `admin` 可以查看待审核列表、通过、拒绝
- 团队 `member` 不能审核
- 非团队成员不能访问审核接口
- 只能审核当前团队下的文档
- 只能审核 `review_status = pending_review` 的文档
- 审核通过后只更新审核状态，不改变 `processing_status`
- 审核拒绝时必须带拒绝原因

待审核列表默认只返回 `pending_review` 文档，返回字段与文档列表一致，包括：

- `id`
- `knowledge_base_id`
- `owner_id`
- `submitted_by`
- `filename`
- `original_filename`
- `file_type`
- `file_size`
- `storage_path`
- `review_status`
- `processing_status`
- `reviewed_by`
- `reviewed_at`
- `review_comment`
- `created_at`
- `updated_at`

审核通过后的关键变化：

- `review_status = approved`
- `reviewed_by = current_user.id`
- `reviewed_at = 当前时间`
- `processing_status` 仍保持 `uploaded`

审核拒绝后的关键变化：

- `review_status = rejected`
- `reviewed_by = current_user.id`
- `reviewed_at = 当前时间`
- `review_comment = 拒绝原因`
- `processing_status` 仍保持 `uploaded`

示例：

```bash
curl http://127.0.0.1:8000/api/v1/teams/<team_id>/review-tasks \
  -H "Authorization: Bearer <admin_token>"
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/documents/<document_id>/approve \
  -H "Authorization: Bearer <admin_token>"
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/teams/<team_id>/documents/<document_id>/reject \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"review_comment":"File content does not meet team policy."}'
```

如何验证权限和重复审核：

1. 成员向团队知识库提交一份文档，此时应为 `pending_review`
2. 团队 `admin` 调 `GET /review-tasks`，应看到该文档
3. 团队 `member` 调 `GET /review-tasks` 或 `POST /approve`，应返回 `403`
4. 非成员访问同样接口，应返回 `404`
5. `admin` 审核通过后，再次调用 `approve` 或 `reject`，应返回 `409`
6. `admin` 审核拒绝后，列表中不再出现该文档，且返回里有 `review_comment`

## 认证接口

当前已提供最小认证闭环接口：

- `POST /api/v1/auth/register`：注册用户
- `POST /api/v1/auth/login`：登录并获取 access token
- `GET /api/v1/users/me`：获取当前登录用户信息

### 注册

请求体示例：

```json
{
  "email": "alice@example.com",
  "username": "alice",
  "password": "StrongPass123"
}
```

### 登录

请求体示例：

```json
{
  "identifier": "alice@example.com",
  "password": "StrongPass123"
}
```

返回示例：

```json
{
  "access_token": "<jwt-token>",
  "token_type": "bearer"
}
```

### 使用 Token 访问受保护接口

登录成功后，把 token 放到 `Authorization` 请求头：

```text
Authorization: Bearer <jwt-token>
```

示例：

```bash
curl http://127.0.0.1:8000/api/v1/users/me \
  -H "Authorization: Bearer <jwt-token>"
```

### 本地验证认证闭环

先启动服务：

```bash
python -m uvicorn app.main:app --reload
```

然后依次执行：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","username":"alice","password":"StrongPass123"}'
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"alice@example.com","password":"StrongPass123"}'
```

把返回的 `access_token` 填入下面请求：

```bash
curl http://127.0.0.1:8000/api/v1/users/me \
  -H "Authorization: Bearer <access_token>"
```

## 个人知识库接口

当前已提供最小个人知识库 CRUD 接口，全部要求登录，并且只允许操作当前用户自己的知识库：

- `POST /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{knowledge_base_id}`
- `PATCH /api/v1/knowledge-bases/{knowledge_base_id}`
- `DELETE /api/v1/knowledge-bases/{knowledge_base_id}`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`
- `GET /api/v1/knowledge-bases/{knowledge_base_id}/documents`

所有请求都需要带上：

```text
Authorization: Bearer <access_token>
```

### 创建知识库

请求体示例：

```json
{
  "name": "Engineering Docs",
  "description": "Team internal knowledge base"
}
```

返回字段：

- `id`
- `name`
- `description`
- `scope`
- `owner_id`
- `team_id`
- `created_at`
- `updated_at`

### 列表与详情

- 列表接口只返回当前登录用户自己的知识库
- 详情接口只允许读取当前用户自己的知识库

### 更新知识库

请求体示例：

```json
{
  "name": "Engineering Knowledge Base",
  "description": "Updated description"
}
```

`PATCH` 只更新请求体中显式传入的字段。

### 删除知识库

删除成功返回 `204 No Content`。

### 本地验证知识库 CRUD 与归属隔离

先确保服务已经启动，再准备两个用户并分别登录，拿到两个 token。

Alice 创建知识库：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases \
  -H "Authorization: Bearer <alice_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice KB","description":"Alice private data"}'
```

Alice 查看自己的知识库列表：

```bash
curl http://127.0.0.1:8000/api/v1/knowledge-bases \
  -H "Authorization: Bearer <alice_token>"
```

Bob 查看自己的知识库列表，应该看不到 Alice 的知识库：

```bash
curl http://127.0.0.1:8000/api/v1/knowledge-bases \
  -H "Authorization: Bearer <bob_token>"
```

Bob 直接访问 Alice 的知识库详情，应该返回 `404`：

```bash
curl http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id> \
  -H "Authorization: Bearer <bob_token>"
```

Alice 更新自己的知识库：

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id> \
  -H "Authorization: Bearer <alice_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice KB Updated","description":"Updated"}'
```

Alice 删除自己的知识库：

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id> \
  -H "Authorization: Bearer <alice_token>"
```

### 个人知识库文档上传与列表

个人知识库文档接口：

- 上传接口：`POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`
- 列表接口：`GET /api/v1/knowledge-bases/{knowledge_base_id}/documents`
- 解析接口：`POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse`
- chunk 接口：`POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk`
- embedding 接口：`POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed`
- 检索接口：`POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieve`

个人文档上传规则：

- 文件保存到 `${UPLOAD_DIR}/personal/knowledge_base_{knowledge_base_id}/`
- 上传时写入 `review_status = not_required`
- 上传时写入 `processing_status = uploaded`
- 只有知识库所有者可以上传和查看列表

上传请求使用 `multipart/form-data`，字段名固定为 `file`。

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents \
  -H "Authorization: Bearer <alice_token>" \
  -F "file=@./alice-notes.txt"
```

```bash
curl http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents \
  -H "Authorization: Bearer <alice_token>"
```

成功后你应该看到：

- `review_status = not_required`
- `processing_status = uploaded`

如果 Bob 访问 Alice 的文档列表或向 Alice 的个人知识库上传文档，应该返回 `404`。

### 个人知识库文档解析

个人文档解析规则：

- 只有知识库所有者可以触发解析
- 只有 `review_status = not_required` 的个人文档可以进入解析
- 当前只支持 `.txt` 和 `.md`
- 解析成功后写入 `${PARSED_DIR}/personal/knowledge_base_{knowledge_base_id}/document_{document_id}.json`
- 解析成功后更新 `processing_status = parsed`
- 解析失败后更新 `processing_status = failed`
- chunk 成功后写入 `${CHUNK_DIR}/personal/knowledge_base_{knowledge_base_id}/document_{document_id}.json`
- chunk 本身不会改变 `processing_status`，文档仍保持 `parsed`

个人文档解析任务接口：

- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks`

这些任务创建成功后都会返回一个 `pending` 状态的任务，后续可以通过 `GET /api/v1/document-tasks/{task_id}` 查询。

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge-bases/<knowledge_base_id>/documents/<document_id>/parse \
  -H "Authorization: Bearer <alice_token>"
```

如果上传的是 `.pdf` 等当前不支持的格式，解析接口会返回 `400`，并且该文档的 `processing_status` 会变成 `failed`。

### 验证数据库连通与建表

迁移完成后，可执行：

```bash
python scripts/verify_db.py
```

如果你希望直接用 `psql` 验证，也可以执行：

```bash
psql postgresql://purelink:purelink@localhost:5432/purelink -c "\dt"
psql postgresql://purelink:purelink@localhost:5432/purelink -c "SELECT * FROM alembic_version;"
```

M4.5 之后，你应该还能看到：

- `teams`
- `team_members`
- `team_invites`

## 运行测试

完成依赖安装后，可在项目根目录执行：

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m pytest
```

当前测试覆盖：

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/users/me`
- `POST /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{knowledge_base_id}`
- `PATCH /api/v1/knowledge-bases/{knowledge_base_id}`
- `DELETE /api/v1/knowledge-bases/{knowledge_base_id}`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`
- `GET /api/v1/knowledge-bases/{knowledge_base_id}/documents`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks`
- `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieve`
- `GET /api/v1/document-tasks/{task_id}`
- `POST /api/v1/teams`
- `GET /api/v1/teams`
- `GET /api/v1/teams/{team_id}`
- `POST /api/v1/teams/{team_id}/invites`
- `GET /api/v1/teams/{team_id}/invites`
- `POST /api/v1/team-invites/join`
- `GET /api/v1/teams/{team_id}/members`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents`
- `GET /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/parse-tasks`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/chunk-tasks`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/embed-tasks`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/documents/{document_id}/index-tasks`
- `POST /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/retrieve`
- 团队域模型的基础建模与 personal/team scope 兼容性
- `GET /api/v1/health` 健康检查接口

## WSL 常见环境问题

如果创建虚拟环境时报 `ensurepip is not available`，或者 `python3 -m pip` 不可用，需要先安装系统包：

```bash
sudo apt update
sudo apt install -y python3.12-venv python3-pip
```

## 后续方向

在第一阶段完成后，再逐步推进以下内容：

- 配置管理与环境变量约束
- API 路由拆分与版本化
- 数据库接入
- Redis 接入
- 文档切片、Embedding、向量检索与 RAG
- Docker 化部署完善

## 说明

- 当前仓库只提供后端底座，不代表最终系统形态
- 数据库、缓存、RAG 相关能力会在后续阶段按计划接入
- 详细阶段拆分请见 `PLAN.md`
