# PureLink Frontend

Next.js App Router frontend for the PureLink backend.

## Stack

- Next.js
- TypeScript
- Tailwind CSS
- TanStack Query
- React Hook Form
- Zod
- shadcn-style UI primitives

## Language Switching

- Built-in `EN / 中文` toggle
- Available on both auth pages and the dashboard
- Selected locale is stored in `localStorage` under `purelink_locale`
- Browser language defaults to Chinese when `navigator.language` starts with `zh`

## Run Locally

```bash
cd /home/pmk/projects/purelink/frontend
cp .env.example .env.local
npm install
npm run dev
```

Frontend default URL:

- `http://127.0.0.1:3000`

Backend API default URL:

- `http://127.0.0.1:8000/api/v1`

If your backend is running elsewhere, update `NEXT_PUBLIC_API_BASE_URL` in `.env.local`.

## Processing Behavior

- The frontend `开始处理 / Start processing` action currently calls the synchronous backend `parse -> chunk -> embed` endpoints in sequence.
- This means manual frontend verification does not require the Go worker by default.
- The Go worker is still used for `document_tasks`, scripted E2E flows, and worker-specific verification.
