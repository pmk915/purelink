# PureLink

> AI-powered knowledge base and task assistant backend for internal teams  
> 面向团队内部文档管理的 AI 知识库与任务助手后端

PureLink is a runnable backend prototype for personal and team knowledge bases. It supports document upload, review workflow, parsing, chunking, embedding, retrieval, and a minimal Q&A flow.  
PureLink 是一个可运行的后端原型，面向个人知识库和团队知识库场景，当前已经打通文档上传、审核、解析、切块、Embedding、检索和最小问答闭环。

This repository is suitable for local development, technical demos, portfolio presentation, and interview walkthroughs.  
这个仓库适合本地开发、技术演示、作品集展示，以及面试中的项目讲解。

## Overview | 项目概览

- Personal knowledge bases with ownership isolation  
  支持个人知识库，具备严格的资源归属隔离
- Team knowledge bases with invitation and member management  
  支持团队知识库、邀请码入队和成员管理
- Team document review workflow before retrieval  
  支持团队文档审核流，审核通过后才能进入检索链路
- Local document processing pipeline for `.txt` and `.md`  
  支持 `.txt` 和 `.md` 文件的本地文档处理流水线
- Conversation and message persistence for Q&A history  
  支持问答会话与消息持久化，便于后续历史展示
- Unified `document_tasks` model with Python API + Go worker  
  通过统一的 `document_tasks` 模型，把 Python API 和 Go worker 串起来

## Features | 当前能力

### Auth and Multi-Tenant Access | 认证与多租户访问控制

- User registration, login, JWT authentication, current-user API  
  用户注册、登录、JWT 鉴权、当前用户查询
- Personal knowledge base CRUD  
  个人知识库 CRUD
- Team creation, invitation, join flow, and member listing  
  团队创建、邀请码生成、入队流程和成员列表
- Team admin / member permission boundaries  
  团队管理员与成员权限边界

### Document Pipeline | 文档处理链

- Upload documents into personal or team knowledge bases  
  文档可上传到个人或团队知识库
- Team documents require admin approval before retrieval  
  团队文档必须先审核通过，才能进入检索链路
- Parse -> chunk -> embed / index task chain  
  支持 parse -> chunk -> embed / index 任务链
- Frontend-triggered processing uses synchronous `parse -> chunk -> embed` by default  
  前端“开始处理”默认直接走同步 `parse -> chunk -> embed` 闭环，本地联调不强依赖 worker
- Local runtime artifacts stored in `data/uploads`, `data/parsed`, `data/chunks`, `data/vector_store`  
  中间产物本地落盘，路径清晰可检查

### Retrieval and Q&A | 检索与问答

- Minimal local embedding and retrieval layer  
  最小本地 embedding 与检索层
- Minimal ask API with citations  
  最小问答接口，返回 answer 和 citations
- Conversation and message persistence with citation metadata  
  回答消息可持久化 citations 元数据
- Switchable answer generator: heuristic or OpenAI-compatible LLM  
  问答生成器可在 heuristic 和 OpenAI-compatible LLM 之间切换

### Engineering and Delivery | 工程化与交付

- FastAPI + PostgreSQL + SQLAlchemy + Alembic  
  FastAPI + PostgreSQL + SQLAlchemy + Alembic
- Go worker for parse / chunk / embed / index tasks  
  Go worker 负责 parse / chunk / embed / index 任务
- Docker Compose local stack  
  Docker Compose 本地一键启动
- Next.js frontend MVP in `frontend/`  
  `frontend/` 目录下提供了可运行的 Next.js 前端 MVP
- Bash E2E scripts for demo and smoke verification  
  Bash E2E 脚本可直接用于演示和冒烟验证
- GitHub Actions CI + smoke workflow  
  已补最小 CI 与 smoke workflow

## Tech Stack | 技术栈

- API: FastAPI
- Database: PostgreSQL
- ORM / Migration: SQLAlchemy 2.0 + Alembic
- Worker: Go
- Storage: local filesystem
- Testing: pytest + Bash E2E + Go test
- Deployment: Docker / Docker Compose

## Architecture | 架构说明

```text
Client
  -> FastAPI API
  -> PostgreSQL
  -> document_tasks
  -> Go worker
  -> local artifacts (uploads / parsed / chunks / vector_store)
  -> retrieval / ask
```

Key design choices:  
核心设计取舍：

- Keep the system runnable locally without heavy external infrastructure  
  先保证本地可运行，不引入过重的外部基础设施
- Use PostgreSQL as both business storage and task coordination source  
  使用 PostgreSQL 同时承载业务数据和任务协调
- Use local files as explicit intermediate artifacts for debugging and demos  
  用本地文件保存中间产物，方便调试和演示
- Keep worker boundaries clean for future queue or object-storage upgrades  
  保留清晰的 worker 边界，后续便于升级到对象存储或队列系统

## Quick Start | 快速启动

### Docker Compose | Docker 一键启动

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
make up
```

Then open:  
启动后访问：

- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

Stop services:  
停止服务：

```bash
make down
```

### Run Without Docker | 非 Docker 方式启动

```bash
cd /home/pmk/projects/purelink
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

You still need PostgreSQL available through `DATABASE_URL`.  
这种方式仍然要求你本地有可用的 PostgreSQL，并且 `DATABASE_URL` 配置正确。

### Frontend MVP | 前端 MVP 启动

```bash
cd /home/pmk/projects/purelink/frontend
cp .env.example .env.local
npm install
npm run dev
```

Then open:  
启动后访问：

- Frontend: `http://127.0.0.1:3000`
- Backend API: `http://127.0.0.1:8000/api/v1`

## Verification | 验证方式

### Local Tests | 本地测试

```bash
cd /home/pmk/projects/purelink
make test
```

### Minimal Smoke Flow | 最小冒烟验证

```bash
cd /home/pmk/projects/purelink
make smoke
```

### Full End-to-End Validation | 完整 E2E 验证

```bash
cd /home/pmk/projects/purelink
make e2e
```

Recommended command sets:  
推荐按下面两种场景执行：

- Manual frontend-backend verification: start `api` and `frontend`, then register, create a knowledge base, upload a `.txt` or `.md`, click `开始处理`, and verify retrieval / ask. This path does not require the Go worker by default.  
  手动前后端联调：启动 `api` 和 `frontend` 后，注册、创建知识库、上传 `.txt/.md`、点击“开始处理”、再验证检索和问答。这条路径默认不强依赖 Go worker。
- Full scripted E2E and worker verification: use `make smoke` or `make e2e`, which both expect the full `db / api / worker` stack from `docker compose`.  
  脚本式全流程和 worker 验证：使用 `make smoke` 或 `make e2e`，这两条命令都依赖 `docker compose` 拉起完整的 `db / api / worker` 环境。

Current E2E coverage:  
当前 E2E 覆盖：

- personal flow  
  个人知识库主链路
- team review flow  
  团队邀请、上传、审核、检索与问答
- permission flow  
  权限边界验证
- worker flow  
  worker 执行与中间产物落盘

## Project Structure | 项目结构

```text
purelink/
├── app/                 # FastAPI app, models, schemas, services
├── alembic/             # Database migrations
├── frontend/            # Next.js frontend MVP
├── worker-go/           # Go worker
├── scripts/e2e/         # Bash end-to-end test scripts
├── tests/               # Python tests and fixtures
├── docs/                # Design notes
├── data/                # Local runtime artifacts
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── README.md
└── DEVELOPMENT_LOG.md
```

## Documentation | 文档入口

- [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md): full milestone history and implementation notes  
  开发日志，包含详细里程碑、接口说明和实现记录
- [test.md](test.md): practical frontend-backend and full-flow verification guide  
  前后端联调与全流程验证手册
- [frontend/README.md](frontend/README.md): frontend setup and local run guide  
  前端启动说明
- [PLAN.md](PLAN.md): roadmap and milestone planning  
  路线图和阶段计划
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution workflow  
  贡献说明
- [AGENTS.md](AGENTS.md): repository working constraints used during development  
  仓库开发约束

## Why This Repo Works Well for Demo | 为什么适合演示和面试展示

- It has a complete backend chain instead of isolated demos  
  它不是零散 demo，而是一条完整的后端业务链
- It includes auth, permissions, review workflow, processing pipeline, retrieval, and Q&A  
  它覆盖了认证、权限、审核流、处理流水线、检索和问答
- It is runnable locally with Docker  
  可以直接在本地拉起运行
- It already has smoke and E2E verification  
  已有 smoke 和 E2E 验证脚本
- The architecture leaves room for future scale-up  
  架构上为后续扩展预留了清晰边界

## Roadmap | 后续方向

- stronger production deployment packaging  
  更完整的生产部署方案
- more robust retrieval and ranking  
  更强的检索与排序能力
- optional external embedding and vector backends  
  可选的外部 embedding 与向量后端
- richer Q&A orchestration and prompt strategy  
  更丰富的问答编排与 prompt 策略
- eventual frontend integration  
  后续前端接入

## License | 许可证

This project is released under the MIT License. See [LICENSE](LICENSE).  
本项目基于 MIT License 开源，见 [LICENSE](LICENSE)。
