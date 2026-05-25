# PureLink M13 Upgrade Plan: LightRAG-inspired Knowledge Base Workspace

## Goal

M13 upgrades the knowledge base detail page from a simple document/Q&A view into a clearer RAG workspace inspired by mature RAG WebUIs such as LightRAG.

PureLink will keep its own product model: personal/team knowledge bases, permissions, document review, citation grounding, retrieval trace, index metadata, and lightweight GraphRAG. M13 does not copy LightRAG internals or add a full graph canvas.

## Workspace Tabs

Both personal and team KB workspaces should expose a consistent tab layout:

- Ask
- Documents
- Graph
- Retrieval Debug
- Health
- Settings

Visibility rules:

- Personal KB owner sees all tabs.
- Team admin sees all tabs.
- Team member sees Ask, Documents, Graph, and Health.
- Backend permissions remain authoritative.

## Ask and Evidence

The Ask tab should show:

- question input
- current answer
- evidence/citation panel
- collapsed retrieval details

Normal users should see source-oriented labels. Technical details stay behind a collapsed section.

## Documents and Health

Documents should remain the indexing dashboard:

- processing status
- review status
- retry/delete actions where allowed
- useful index health summary

The Health tab should reuse M12 health summary data for document, vector index, and graph index counts.

## Graph

M13 adds a lightweight graph explorer:

- entity search
- entity list
- selected entity detail
- mentions
- connected relations with source references

No complex graph visualization is required.

## Retrieval Debug

Owner/admin users can run direct retrieval:

- query
- mode
- top_k
- candidate list
- source/snippet/score details

This should use existing retrieval endpoints where possible.

## Non-goals

- No Agent runtime.
- No LangChain/LangGraph.
- No MCP server.
- No external graph database.
- No full LightRAG clone.
- No complex multi-hop graph reasoning.
- No retrieval ranking change.
- No full multimodal RAG.

## Validation

Run:

```bash
.venv/bin/python -m pytest tests/test_knowledge_bases.py tests/test_team_knowledge_bases.py
cd frontend && npm run lint && npm run build && cd ..
git diff --check
```

Run broader `make test` and smoke before merging.
