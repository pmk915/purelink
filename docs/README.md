# PureLink Documentation Index

This page is the main map for PureLink's product, RAG architecture, ingestion, GraphRAG, development, and interview demo documentation.

## Product

- [Knowledge Base Workspace](product/kb-workspace.md): Ask, Documents, Graph, Retrieval Debug, Health, and Settings tabs.
- [Knowledge Base Management](product/knowledge-base-management.md): personal and team KB management.
- [RAG Answer Experience](product/rag-answer-experience.md): answer, citation, and source evidence UX.
- [Document Processing Inspector](product/kb-workspace.md#document-processing-inspector): document-level RAG readiness and debug JSON.
- [Processing Job Dashboard](product/kb-workspace.md#processing-job-dashboard): KB-level processing jobs, failure details, and retry.
- [Upload Limits and Validation](product/kb-workspace.md#upload-limits-and-validation): supported file types, max upload size, and upload error handling.
- [Graph Explorer](product/kb-workspace.md#graph-explorer): entity search, relation filters, one-hop neighborhood, source inspection, and export.

## RAG Architecture

- [RAG v2 Architecture](architecture/rag-v2-architecture.md): high-level RAG v2 design.
- [RAG Pipeline](rag/rag-pipeline.md): ingestion-to-retrieval flow.
- [Retrieval Layer](rag/retrieval-layer.md): retrieval modes, router, and service boundary.
- [Retrieval and Citations](retrieval-and-citations.md): evidence selection and citation grounding.
- [Retrieval Trace](rag/retrieval-trace.md): trace metadata for debugging retrieval.
- [Model Providers](rag/model-providers.md): embedding, reranker, and LLM provider boundaries.
- [Optional Reranker](rag/reranker.md): reranker configuration and behavior.
- [Index Metadata](rag/index-metadata.md): vector index compatibility and stale index safety.
- [RAG Evaluation](rag/rag-evaluation.md): deterministic retrieval/citation eval harness.
- [RAG Eval Baseline Summary](interview/rag-eval-baseline-summary.md): M18 baseline results and findings.

## Ingestion

- [File Processing Pipeline](ingestion/file-processing-pipeline.md): upload, parsing, blocks, chunks, citations, vector index, and graph index.
- [Document Blocks](ingestion/document-blocks.md): `DocumentBlock` schema and parser routing.
- [Processing Pipeline](processing-pipeline.md): earlier processing flow notes.
- [Job State Machine](job-state-machine.md): processing job lifecycle.

## GraphRAG

- [Lightweight GraphRAG](rag/lightweight-graphrag.md): graph schema, extraction, lifecycle cleanup, export, and Explorer UI.
- [Graph Lifecycle](rag/lightweight-graphrag.md#lifecycle-maintenance): delete/rebuild/cleanup/deduplicate/export operations.
- [Graph Explorer](rag/lightweight-graphrag.md#graph-explorer-ui): list-based graph browsing and source provenance.

## Development

- [Testing and Smoke](development/testing-and-smoke.md): unit tests, smoke, eval, and demo verification.
- [Development Commands](development/dev-commands.md): common local commands.
- [Docker Deployment](development/docker-deployment.md): local and production-like Docker Compose, env files, backup/restore, and troubleshooting.
- [Error Handling](development/error-handling.md): API error envelope, request ids, frontend error states, and troubleshooting.
- [Release Checklist](development/release-checklist.md): final verification, docs checks, data hygiene, and optional tag commands.
- [Frontend-Backend Integration Test](development/frontend-backend-integration-test.md): local integration checks.
- [Troubleshooting](troubleshooting.md): operational and debugging notes.
- [Environment Variables](../.env.example): local configuration template.

## Interview

- [PureLink Interview Demo Guide](interview/purelink-demo-guide.md): step-by-step demo runbook.
- [Project Storyline](interview/project-storyline.md): problem, solution, engineering decisions, timeline, and talk tracks.
- [Feature Map](interview/feature-map.md): feature-to-code-to-docs-to-tests mapping.
- [Eval Talking Points](interview/eval-talking-points.md): how to explain the RAG baseline honestly.
- [RAG Project Story](interview/purelink-rag-project-story.md): earlier RAG v2 project narrative.
- [RAG Resume Description](interview/purelink-rag-resume-description.md): resume-oriented summary.
- [RAG v2 Demo Guide](interview/rag-v2-demo-guide.md): older RAG v2 focused demo flow.

## Roadmap and Historical Notes

Roadmap files are historical implementation notes. The current project entry
points are [README](../README.md), this docs index, and the interview docs above.

- [PLAN](../PLAN.md)
- [Development Log](../DEVELOPMENT_LOG.md)
- [Project Notes](project-notes.md)
- [Team Domain Model](team_domain_model.md)
- [Roadmap docs](roadmap/)
