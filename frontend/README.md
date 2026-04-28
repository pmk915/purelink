# PureLink Frontend

PureLink 前端基于 Next.js App Router，用于连接 PureLink FastAPI 后端。

## 技术栈

- Next.js
- TypeScript
- Tailwind CSS
- TanStack Query
- React Hook Form
- Zod
- shadcn-style UI primitives

## 语言切换

- 内置 `EN / 中文` 切换
- 登录、注册和工作台页面都可用
- 语言选择保存在 `localStorage` 的 `purelink_locale`
- 当 `navigator.language` 以 `zh` 开头时，默认使用中文

## 本地运行

```bash
cd /home/pmk/projects/purelink/frontend
cp .env.example .env.local
npm install
npm run dev
```

前端默认地址：

- `http://127.0.0.1:3000`

后端 API 默认地址：

- `http://127.0.0.1:8000/api/v1`

如果后端不在默认地址，修改 `.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL`。

## 使用 Docker Compose 运行

仓库根目录的 `docker-compose.yml` 已包含 frontend 服务。

```bash
cd /home/pmk/projects/purelink
cp .env.example .env
docker compose up -d --build frontend
```

Docker 镜像会构建 Next.js standalone production server。`NEXT_PUBLIC_API_BASE_URL` 是构建时变量，修改后需要重新构建 frontend 镜像。

## 文档准备行为

- 个人上传和审核通过的团队上传会自动提交到后端 `/process` job flow。
- 团队管理员上传免审核；团队成员上传需要等待管理员审核。
- 文本、图片 OCR、扫描 PDF OCR、音频转写、视频转写都会进入 `DocumentChunk -> ready -> indexed -> retrieve / ask` 主路径。
- Citation 卡片使用结构化 `source_locator`，用于展示 PDF 页码、OCR 区域、文本章节和音频/视频时间段。
- `parse -> chunk -> embed` legacy path 仍保留给兼容脚本、`document_tasks` 和 worker 验证使用，不建议新功能继续扩展。
