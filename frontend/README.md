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

- The frontend `开始处理 / Start processing` action now sends `.txt`, `.md`, `.pdf`, `.docx`, `.mp3`, `.wav`, `.m4a`, `.mp4`, `.mov`, `.m4v`, `.png`, `.jpg`, and `.jpeg` documents to the backend `/process` entry.
- Text, image OCR, scanned PDF OCR, audio transcription, and video transcription all converge into the same `DocumentChunk -> ready -> indexed -> retrieve / ask` pipeline.
- Citation cards consume structured `source_locator` data so they can show PDF pages, OCR text regions, text sections, and audio/video time ranges without guessing from loose fields.
- The legacy `parse -> chunk -> embed` path is still available for compatibility, including worker-driven `document_tasks`, scripted E2E flows, and worker-specific verification.
