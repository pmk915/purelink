# Error Handling

M21.1 standardizes failed API responses without changing successful response
shapes.

## Backend Error Envelope

Failed API responses use:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Knowledge base not found.",
    "details": {
      "resource": "knowledge_base"
    },
    "request_id": "req_..."
  }
}
```

The backend also returns the same request id in the `X-Request-ID` response
header. If the client sends `X-Request-ID`, PureLink preserves it; otherwise the
API generates a `req_...` id.

Stable codes include:

- `UNAUTHORIZED`
- `FORBIDDEN`
- `RESOURCE_NOT_FOUND`
- `VALIDATION_ERROR`
- `CONFLICT`
- `RATE_LIMITED`
- `UPLOAD_TOO_LARGE`
- `UNSUPPORTED_FILE_TYPE`
- `DOCUMENT_NOT_READY`
- `DOCUMENT_PROCESSING_FAILED`
- `VECTOR_INDEX_NOT_READY`
- `GRAPH_INDEX_NOT_READY`
- `RETRIEVAL_FAILED`
- `GRAPH_EXPORT_FAILED`
- `BAD_REQUEST`
- `INTERNAL_ERROR`

Legacy FastAPI `detail` payloads remain supported. A `detail` string becomes the
message. A `detail` object with `code`/`error_code` and `message` preserves those
business values.

Unhandled exceptions are logged with `request_id` and return `INTERNAL_ERROR`.
Responses must not expose stack traces, secrets, or absolute local paths.

## Frontend Handling

The frontend API client parses the new `error` envelope first, then falls back to
legacy `detail` payloads and status text. Network failures use
`NETWORK_ERROR`.

Shared UI states live under `frontend/components/common/`:

- `ErrorState`
- `EmptyState`
- `LoadingState`

These states are used in the KB workspace, Documents list, Document Processing
Inspector, Graph Explorer, Ask workspace, and Retrieval Debug surfaces. Where a
retry is available, the UI shows the existing query or mutation retry action.

## Troubleshooting

When a user reports a UI failure, ask for:

- visible error code
- request id
- page or action
- approximate time

Then search backend logs by `request_id`. The request id is safe to share; stack
traces and sensitive configuration values are not shown in frontend responses.
