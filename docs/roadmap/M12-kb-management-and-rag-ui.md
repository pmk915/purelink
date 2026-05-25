# PureLink M12 Upgrade Plan: Knowledge Base Management and RAG Evidence UI

## Goal

M12 turns the RAG v2 backend into a more visible user experience.

It has two tracks:

1. Knowledge base management
   - Personal KB owner delete with confirmation.
   - Team KB admin-only delete.
   - Frontend refresh, success state, and error state after delete.
2. RAG evidence UI
   - Answer citations and evidence snippets.
   - Retrieval/debug details when metadata exists.
   - Knowledge base RAG health summary.
   - Document processing and index status cues.

## Non-goals

- No Agent runtime.
- No LangChain or LangGraph.
- No MCP server.
- No full multimodal support.
- No Neo4j or external graph database.
- No retrieval ranking behavior change.
- No complex graph visualization.

## Backend Scope

- Audit personal and team KB delete APIs.
- Preserve backend permission checks:
  - personal KB delete: owner only
  - team KB delete: admin only
- Add a lightweight RAG health endpoint if needed:
  - `GET /api/v1/knowledge-bases/{knowledge_base_id}/rag-health`
  - `GET /api/v1/teams/{team_id}/knowledge-bases/{knowledge_base_id}/rag-health`
- Health summary should include:
  - document count
  - document processing status counts
  - vector index status counts
  - graph index status counts

## Frontend Scope

- Add safe delete actions for personal and team KBs.
- Reuse the existing confirm dialog.
- Hide or disable team KB delete for non-admins.
- Show friendly success and failure messages.
- Add a compact RAG health panel on the KB workspace.
- Keep citations visible and source-oriented:
  - marker
  - document name
  - source locator
  - snippet
- Add a collapsed retrieval details area where data exists.

## Documentation Scope

- Add user docs:
  - `docs/product/knowledge-base-management.md`
  - `docs/product/rag-answer-experience.md`
- Update `docs/README.md`.
- Update README with a concise product-facing note.

## Validation

Run:

```bash
.venv/bin/python -m pytest tests/test_knowledge_bases.py tests/test_team_knowledge_bases.py tests/services/retrieval tests/eval
make test
make KEEP_STACK_UP=1 smoke
make smoke-docx-rag
cd frontend
npm run lint
npm run build
cd ..
git diff --check
```

## Acceptance Criteria

- Personal KB owner can delete from UI with confirmation.
- Non-owner cannot delete through backend.
- Team KB delete is admin-only through backend and UI.
- Delete success refreshes or redirects safely.
- Ask/conversation UI shows citations with document, locator, and snippet.
- KB workspace shows document/RAG health summary.
- Existing ask and citation behavior remains unchanged.
- Backend tests, frontend build, smoke tests, and diff check pass.
