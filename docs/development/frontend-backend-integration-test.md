# PureLink Frontend-Backend Integration Test

这份文档只解决一个问题：
如何快速确认 PureLink 的前端和后端已经打通。

默认约定：

- 后端地址：`http://127.0.0.1:8000`
- 后端 API 前缀：`http://127.0.0.1:8000/api/v1`
- 前端地址：`http://127.0.0.1:3000`
- 项目根目录：`/home/pmk/projects/purelink`

---

## 1. 测什么

如果下面 4 件事都成功，基本就可以认为前后端已经打通：

1. 后端服务能启动，健康检查接口可访问
2. 前端页面能启动并正常打开
3. 前端可以成功调用后端认证接口
4. 登录后前端可以读取并展示后端真实数据

补充一条当前版本的重要约定：

- 前端页面里的“开始处理”默认直接走同步 `parse -> chunk -> embed` 闭环
- 所以手动联调前后端时，不要求必须先启动 Go worker
- 但如果你要跑 `make smoke`、`make e2e` 或 `scripts/e2e/*.sh`，仍然要使用完整的 `db / api / worker` 环境

---

## 2. 测试前准备

先确认这几个文件存在并且配置正确：

### 后端环境

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
```

重点检查 `.env` 里的数据库连接是否可用，至少要保证：

- `DATABASE_URL` 指向一个你本地可连接的 PostgreSQL

### 前端环境

```bash
cd /home/pmk/projects/purelink/frontend
cp .env.example .env.local
```

默认前端会请求：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

如果你的后端不是跑在 `127.0.0.1:8000`，这里必须改。

---

## 3. 启动后端

在第一个终端里执行：

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

如果你还没装依赖，先执行：

```bash
cd /home/pmk/projects/purelink
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 后端成功标准

浏览器打开：

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/api/v1/health`

或者命令行执行：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

预期至少返回 `200`，并且是健康检查 JSON。

---

## 4. 启动前端

在第二个终端里执行：

```bash
cd /home/pmk/projects/purelink/frontend
npm install
npm run dev
```

### 前端成功标准

浏览器打开：

- `http://127.0.0.1:3000`

预期：

- 页面能打开
- 能看到 PureLink 登录或注册界面
- 页面没有白屏
- 浏览器控制台没有大量红色报错

---

## 5. 最小人工联调流程

这是最直接的前后端打通验证方式。

### 步骤 1：注册

打开前端：

- `http://127.0.0.1:3000/register`

输入一组新用户信息：

- email：任意未注册邮箱
- username：任意未占用用户名
- password：符合当前后端校验规则的密码

预期：

- 前端提交成功
- 后端产生新用户
- 页面跳转到登录后页面，或者自动登录进入 dashboard

如果失败，打开浏览器开发者工具的 `Network` 看这次请求：

- 请求地址应是 `http://127.0.0.1:8000/api/v1/auth/register`
- 返回码应是 `201`

### 步骤 2：登录

打开：

- `http://127.0.0.1:3000/login`

使用刚注册的用户登录。

预期：

- 登录成功
- 跳转到前端 dashboard
- 说明前端已经成功调用后端 `login` 接口，并拿到 token

### 步骤 3：读取当前用户相关页面

登录后依次打开：

- `http://127.0.0.1:3000/knowledge-bases`
- `http://127.0.0.1:3000/teams`
- `http://127.0.0.1:3000/conversations`

预期：

- 页面能正常展示
- 即使没有数据，也应该显示空状态，而不是报错
- 说明前端已经用登录 token 成功请求后端受保护接口

### 步骤 4：创建一个个人知识库

在前端知识库页面创建一个新的 personal knowledge base。

预期：

- 创建成功
- 列表里立刻出现新知识库

这一步能证明：

- 前端表单提交正常
- 后端创建接口可用
- 前端列表刷新逻辑可用

---

## 6. 用 Network 面板确认是否真的打到后端

这个检查最关键。

打开浏览器开发者工具：

1. 打开 `Network`
2. 勾选 `Preserve log`
3. 在前端执行注册、登录、创建知识库这些动作
4. 查看请求详情

你要重点看这几项：

- Request URL 是否指向 `http://127.0.0.1:8000/api/v1/...`
- Status Code 是否是 `200 / 201`
- Response 是否是后端返回的 JSON
- 登录后的请求头里是否带了 `Authorization: Bearer ...`

如果这些都对，说明前后端不只是“都启动了”，而是真的连上了。

---

## 7. 命令行最小联调验证

如果你想先排除前端问题，可以直接手动打后端接口。

### 健康检查

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### 注册

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo_test@example.com",
    "username": "demo_test_user",
    "password": "StrongPass123"
  }'
```

### 登录

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "identifier": "demo_test@example.com",
    "password": "StrongPass123"
  }'
```

如果这里都成功，而前端失败，问题一般就在：

- `frontend/.env.local` 配错
- 前端请求地址不对
- CORS 配置不对
- 前端 token 保存或读取逻辑有问题

---

## 8. 一键自动化验证

如果你想看完整链路，不只测“是否打通”，还要测主要功能能不能跑，可以直接用仓库现成脚本。

### 后端测试

```bash
cd /home/pmk/projects/purelink
make test
```

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

如果你想跑完后保留容器，方便继续看日志或手动检查数据，可以执行：

```bash
cd /home/pmk/projects/purelink
KEEP_STACK_UP=1 make smoke
KEEP_STACK_UP=1 make e2e
```

如果你只是想验证前后端是否打通，优先顺序建议是：

1. 手动打开前端注册和登录
2. 手动创建一个个人知识库
3. 手动上传一个 `.txt` 或 `.md`
4. 点击“开始处理”，确认文档进入可搜索状态
5. 再跑 `make smoke`

---

## 9. 常见失败点

### 1. 前端能打开，但注册/登录报错

先检查：

- 后端是否真的启动
- `frontend/.env.local` 的 `NEXT_PUBLIC_API_BASE_URL` 是否正确
- 浏览器 `Network` 里请求是否发到了 8000 端口

### 2. 浏览器提示跨域错误

这是 CORS 问题。

你需要检查后端是否允许前端地址，例如：

- `http://127.0.0.1:3000`
- `http://localhost:3000`

如果你前端和后端混用了 `localhost` 和 `127.0.0.1`，也可能导致看起来像“同一台机器”，实际却跨域不一致。

### 3. 后端启动了，但接口 500

通常优先看：

- 数据库是否已启动
- `DATABASE_URL` 是否正确
- Alembic 迁移是否已经执行

建议执行：

```bash
cd /home/pmk/projects/purelink
alembic upgrade head
```

### 4. 登录成功后页面还是空的

这类问题通常是：

- 前端 token 没存好
- 前端后续请求没有带 `Authorization`
- 当前用户接口或列表接口报错

直接看浏览器 `Network` 最快。

---

## 10. 推荐的最短验证路径

如果你只想用 5 分钟确认前后端是否打通，按这个顺序走：

1. 启动后端
2. `curl http://127.0.0.1:8000/api/v1/health`
3. 启动前端
4. 打开 `http://127.0.0.1:3000/register`
5. 注册一个新用户
6. 登录进入 dashboard
7. 打开知识库页面并创建一个 personal knowledge base
8. 上传一个 `.txt` 或 `.md`
9. 点击“开始处理”
10. 打开检索或问答，确认能返回结果

这 10 步都通过，就可以认为当前 PureLink 前后端已经打通，而且最小业务闭环也通了。

---

## 11. 推荐的全流程测试指令

下面给你三组可以直接复制的命令。

### 方案 A：手动前后端联调

适用场景：

- 你想看浏览器页面
- 你想验证注册、登录、上传、处理、检索、问答
- 你不想先依赖 Go worker

终端 1，启动后端：

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

终端 2，启动前端：

```bash
cd /home/pmk/projects/purelink/frontend
npm install
npm run dev
```

终端 3，健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

然后在浏览器里按这个顺序操作：

1. 打开 `http://127.0.0.1:3000/register`
2. 注册并登录
3. 创建个人知识库
4. 上传 `.txt` 或 `.md`
5. 点击“开始处理”
6. 等待文档状态变成可搜索
7. 执行一次 retrieval
8. 再执行一次 ask

### 方案 B：Docker 全流程自动验证

适用场景：

- 你想一键拉起 `db / api / worker`
- 你想直接跑仓库内 Bash E2E
- 你想验证 worker 路径和中间产物落盘

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
make up
make smoke
make e2e
```

如果你想看日志：

```bash
cd /home/pmk/projects/purelink
make logs
```

如果你想跑完后不自动清栈：

```bash
cd /home/pmk/projects/purelink
KEEP_STACK_UP=1 make e2e
```

### 方案 C：本地 worker 路径验证

适用场景：

- 你想单独确认 Go worker 会消费 `document_tasks`
- 你想验证任务模式，而不是前端默认的同步处理模式

终端 1，启动后端：

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

终端 2，启动 worker：

```bash
cd /home/pmk/projects/purelink
go run ./worker-go/cmd/parse-worker
```

终端 3，跑最小冒烟：

```bash
cd /home/pmk/projects/purelink
scripts/e2e/01_personal_flow.sh
```

或者直接全跑：

```bash
cd /home/pmk/projects/purelink
scripts/e2e/run_all.sh
```

---

## 12. 推荐你现在就执行的命令

### 终端 1：后端

```bash
cd /home/pmk/projects/purelink
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

### 终端 2：前端

```bash
cd /home/pmk/projects/purelink/frontend
npm install
npm run dev
```

### 终端 3：健康检查

```bash
curl http://127.0.0.1:8000/api/v1/health
```

然后浏览器打开：

- `http://127.0.0.1:3000/register`

先跑注册、登录、创建知识库、上传 `.txt`，再点击“开始处理”。这是当前最直观、最接近真实使用方式的联调验证。
