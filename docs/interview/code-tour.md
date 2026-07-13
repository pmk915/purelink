# PureLink Code Tour

This tour is a ten-minute reading path through PureLink's document-to-answer flow. Every path and symbol below is present in the repository; the linked tests show the behavior at the relevant boundary.

Use this page to answer **where to inspect the code**. For design rationale, end-to-end behavior, trade-offs, and interview follow-ups, continue with the [Technical Deep Dives](deep-dives/README.md).

## 1. Start Here

- **Responsibility:** assemble the FastAPI application, mount `/api/v1`, and expose personal, team, and conversation request paths.
- **Verified code paths:** [`app/main.py`](../../app/main.py), [`app/core/application.py`](../../app/core/application.py), [`app/api/router.py`](../../app/api/router.py), [`app/api/v1/knowledge_bases.py`](../../app/api/v1/knowledge_bases.py), [`app/api/v1/team_knowledge_bases.py`](../../app/api/v1/team_knowledge_bases.py), and [`app/api/v1/conversations.py`](../../app/api/v1/conversations.py).
- **Key entry points:** `create_app()`, `ask_personal_knowledge_base_endpoint()`, `ask_team_knowledge_base_endpoint()`, and `append_conversation_message_endpoint()`.
- **What to look for:** authentication and ownership checks stay in the API layer; processing, retrieval, and QA work are delegated to services.
- **Related tests:** [`tests/test_knowledge_bases.py`](../../tests/test_knowledge_bases.py), [`tests/test_team_knowledge_bases.py`](../../tests/test_team_knowledge_bases.py), and [`tests/test_documents.py`](../../tests/test_documents.py).
- **Design note:** [Knowledge Base Workspace](../product/kb-workspace.md).

## 2. Document Processing

- **Responsibility:** claim queued jobs, parse an uploaded document, persist blocks/chunks/citation units, and enqueue indexing with explicit progress and failure states.
- **Verified code paths:** [`app/services/processing_worker.py`](../../app/services/processing_worker.py), [`app/services/document_processing.py`](../../app/services/document_processing.py), and [`app/services/document_indexing.py`](../../app/services/document_indexing.py).
- **Key entry points:** `execute_processing_job()`, `run_processing_job_worker()`, `process_document()`, `run_indexing_job_worker()`, and `build_document_index()`.
- **What to look for:** processing and indexing are separate job types; `process_document()` reports its current step and rolls back before marking a failed document.
- **Related tests:** [`tests/services/document_parsing/test_processing_integration.py`](../../tests/services/document_parsing/test_processing_integration.py), [`tests/services/indexing/test_document_indexing_integration.py`](../../tests/services/indexing/test_document_indexing_integration.py), and [`tests/test_processing_queue.py`](../../tests/test_processing_queue.py).
- **Design note:** [File Processing Pipeline](../ingestion/file-processing-pipeline.md).

## 3. Parser Routing and Document Blocks

- **Responsibility:** select a parser by filename/MIME type, normalize parser output, and persist ordered typed blocks with source locators and metadata.
- **Verified code paths:** [`app/services/document_parsing/parser_registry.py`](../../app/services/document_parsing/parser_registry.py), [`app/services/document_parsing/block_normalizer.py`](../../app/services/document_parsing/block_normalizer.py), [`app/services/document_parsing/block_persistence.py`](../../app/services/document_parsing/block_persistence.py), and [`app/models/document_block.py`](../../app/models/document_block.py).
- **Key entry points:** `get_parser()`, `assign_block_char_ranges()`, `blocks_to_plain_text()`, and `replace_document_blocks()`.
- **What to look for:** the parser contract returns a `ParsedDocument`; headings, paragraphs, tables, code, pages, and source ranges survive as `DocumentBlock` data rather than being flattened immediately.
- **Related tests:** [`tests/services/document_parsing/test_parser_registry.py`](../../tests/services/document_parsing/test_parser_registry.py), [`tests/services/document_parsing/test_block_normalizer.py`](../../tests/services/document_parsing/test_block_normalizer.py), and [`tests/services/document_parsing/test_block_persistence.py`](../../tests/services/document_parsing/test_block_persistence.py).
- **Design note:** [Document Blocks and Parser Routing](../ingestion/document-blocks.md).

## 4. Block-aware Chunking

- **Responsibility:** turn ordered blocks into bounded chunks while preserving heading, table, code, page, and source-span boundaries.
- **Verified code paths:** [`app/services/document_chunking/block_aware_chunker.py`](../../app/services/document_chunking/block_aware_chunker.py) and [`app/services/document_processing.py`](../../app/services/document_processing.py).
- **Key entry points:** `build_block_aware_chunks()`, `chunk_document_for_processing()`, `build_citation_unit_payloads()`, and `replace_document_chunks()`.
- **What to look for:** heading stacks are attached to section chunks, table/code blocks are handled independently, oversized blocks use bounded splitting, and fixed chunking remains the configured fallback path.
- **Related tests:** [`tests/services/document_chunking/test_block_aware_chunker.py`](../../tests/services/document_chunking/test_block_aware_chunker.py) and [`tests/test_citation_units.py`](../../tests/test_citation_units.py).
- **Design note:** [Document Blocks and Parser Routing](../ingestion/document-blocks.md) and [RAG Pipeline](../rag/rag-pipeline.md).

## 5. Retrieval Entry Point

- **Responsibility:** provide one retrieval contract for mode resolution, compatible-index filtering, candidate retrieval, optional reranking, final context/evidence selection, and trace recording.
- **Verified code paths:** [`app/services/retrieval/retrieval_service.py`](../../app/services/retrieval/retrieval_service.py), [`app/services/retrieval/types.py`](../../app/services/retrieval/types.py), and [`app/services/retrieval/retrieval_router.py`](../../app/services/retrieval/retrieval_router.py).
- **Key entry points:** `retrieve()`, `RetrievalRequest`, `RetrievalResult`, `resolve_mode()`, `_select_context_chunks()`, and `_select_evidence_units()`.
- **What to look for:** `requested_mode`, router-selected mode, effective fallback mode, raw candidates, context chunks, and final evidences remain distinct and are carried into trace metadata.
- **Related tests:** [`tests/test_retrieval_pipeline.py`](../../tests/test_retrieval_pipeline.py), [`tests/services/retrieval/test_retrieval_router.py`](../../tests/services/retrieval/test_retrieval_router.py), and [`tests/services/retrieval/test_trace_integration.py`](../../tests/services/retrieval/test_trace_integration.py).
- **Design note:** [Retrieval Layer](../rag/retrieval-layer.md).

## 6. AUTO Query Router

- **Responsibility:** choose a concrete retrieval mode from explainable query patterns while allowing manual modes to bypass automatic routing.
- **Verified code paths:** [`app/services/retrieval/query_router.py`](../../app/services/retrieval/query_router.py) and [`app/services/retrieval/retrieval_service.py`](../../app/services/retrieval/retrieval_service.py).
- **Key entry points:** `route_query()`, `QueryRouteDecision`, and `_select_retrieval_mode()`.
- **What to look for:** the current decision order checks explicit overview wording, then structured entity relations, then exact technical identifiers after an attribute-question guard; low-confidence queries fall back to `chunk_only` with a reason.
- **Related tests:** [`tests/services/retrieval/test_query_router.py`](../../tests/services/retrieval/test_query_router.py) and [`tests/services/retrieval/test_query_router_holdout.py`](../../tests/services/retrieval/test_query_router_holdout.py).
- **Design note:** [Retrieval Layer](../rag/retrieval-layer.md).

## 7. Hybrid Text Retrieval

- **Responsibility:** combine deterministic keyword candidates with vector candidates without adding a search-server dependency.
- **Verified code paths:** [`app/services/retrieval/hybrid_text_retriever.py`](../../app/services/retrieval/hybrid_text_retriever.py) and [`app/services/retrieval/keyword_retriever.py`](../../app/services/retrieval/keyword_retriever.py).
- **Key entry points:** `retrieve_hybrid_text_chunks()`, `merge_hybrid_text_candidates()`, `extract_query_terms()`, `score_keyword_match()`, and `retrieve_keyword_chunks()`.
- **What to look for:** technical token expansion, independent vector/keyword scores, deterministic merge order, and fallback metadata when keyword retrieval contributes no usable signal.
- **Related tests:** [`tests/services/retrieval/test_hybrid_text_retrieval.py`](../../tests/services/retrieval/test_hybrid_text_retrieval.py) and [`tests/services/retrieval/test_keyword_retriever.py`](../../tests/services/retrieval/test_keyword_retriever.py).
- **Design note:** [RAG Pipeline](../rag/rag-pipeline.md) and [Retrieval Layer](../rag/retrieval-layer.md).

## 8. Lightweight Graph Retrieval

- **Responsibility:** extract and persist a small relational layer, retrieve graph-linked chunks, and merge them with vector candidates.
- **Verified code paths:** [`app/services/knowledge_graph/graph_extractor.py`](../../app/services/knowledge_graph/graph_extractor.py), [`app/services/knowledge_graph/graph_index_service.py`](../../app/services/knowledge_graph/graph_index_service.py), [`app/services/knowledge_graph/graph_retriever.py`](../../app/services/knowledge_graph/graph_retriever.py), and [`app/models/knowledge_graph.py`](../../app/models/knowledge_graph.py).
- **Key entry points:** `extract_graph_from_sources()`, `build_document_graph_index()`, `retrieve_graph_chunks()`, and `merge_graph_and_vector_chunks()`.
- **What to look for:** entities, mentions, relations, and source provenance live in PostgreSQL; graph retrieval augments vector retrieval and falls back when graph candidates are empty or weak.
- **Related tests:** [`tests/services/retrieval/test_graph_vector_mix.py`](../../tests/services/retrieval/test_graph_vector_mix.py), [`tests/services/knowledge_graph/test_graph_index_service.py`](../../tests/services/knowledge_graph/test_graph_index_service.py), and [`tests/services/knowledge_graph/test_graph_lifecycle.py`](../../tests/services/knowledge_graph/test_graph_lifecycle.py).
- **Design note:** [Lightweight GraphRAG](../rag/lightweight-graphrag.md).

## 9. Evidence Support Gate

- **Responsibility:** decide whether final evidence supports the requested entity and intent before answer generation.
- **Verified code path:** [`app/services/evidence_support.py`](../../app/services/evidence_support.py).
- **Key entry points:** `evaluate_evidence_support()` and `EvidenceSupportDecision`.
- **What to look for:** query-type-specific mandatory checks cover definitions, attributes, reasons, relations, exact technical identifiers, overviews, and generic factual questions; aggregate scores do not override a failed mandatory check.
- **Related tests:** [`tests/services/test_evidence_support.py`](../../tests/services/test_evidence_support.py) and [`tests/services/test_evidence_support_holdout.py`](../../tests/services/test_evidence_support_holdout.py).
- **Design note:** [Retrieval and Citations](../retrieval-and-citations.md).

## 10. Answer Policy

- **Responsibility:** convert the support decision and citation readiness into a deterministic provider-call or refusal decision, then validate provider markers.
- **Verified code paths:** [`app/services/answer_policy.py`](../../app/services/answer_policy.py) and [`app/services/qa.py`](../../app/services/qa.py).
- **Key entry points:** `decide_answer_policy()`, `refuse_answer_policy()`, `validate_provider_markers()`, and `_answer_with_context_chunks()`.
- **What to look for:** unsupported or non-citation-ready evidence skips the provider and returns no citations; supported evidence is passed with an allowlist of markers and external knowledge disabled.
- **Related tests:** [`tests/services/test_answer_policy.py`](../../tests/services/test_answer_policy.py) and [`tests/test_retrieval_pipeline.py`](../../tests/test_retrieval_pipeline.py).
- **Design note:** [Answer Policy Contract](../rag/answer-policy.md).

## 11. Citation Construction

- **Responsibility:** convert selected units into canonical evidence, enforce provenance readiness, and return only citations referenced by valid provider markers.
- **Verified code paths:** [`app/services/retrieval/citation_builder.py`](../../app/services/retrieval/citation_builder.py), [`app/services/qa.py`](../../app/services/qa.py), and [`app/models/document_citation_unit.py`](../../app/models/document_citation_unit.py).
- **Key entry points:** `build_evidences()`, `citation_readiness()`, `build_answer_citations()`, and `build_citation_read_from_final_evidence()`.
- **What to look for:** persisted citation unit ids and source locators define readiness; deduplication prefers ready provenance; answer order follows the first valid marker rather than raw retrieval rank.
- **Related tests:** [`tests/services/retrieval/test_citation_readiness.py`](../../tests/services/retrieval/test_citation_readiness.py), [`tests/test_citation_units.py`](../../tests/test_citation_units.py), and [`tests/test_documents.py`](../../tests/test_documents.py).
- **Design note:** [Retrieval and Citations](../retrieval-and-citations.md) and [RAG Answer Experience](../product/rag-answer-experience.md).

## 12. Retrieval Trace

- **Responsibility:** persist routing, candidate scores, filtering, evidence selection, support, and answer-policy metadata without changing the public ask contract.
- **Verified code paths:** [`app/services/retrieval/trace_service.py`](../../app/services/retrieval/trace_service.py), [`app/services/retrieval/trace_types.py`](../../app/services/retrieval/trace_types.py), and [`app/models/retrieval_trace.py`](../../app/models/retrieval_trace.py).
- **Key entry points:** `start_retrieval_trace()`, `record_retrieval_trace_items()`, `finish_retrieval_trace()`, and `merge_retrieval_trace_metadata()`.
- **What to look for:** bounded candidate previews, separate initial/rerank/final ranks, filtering reasons, router fields, citation readiness, support decisions, and provider-call decisions.
- **Related tests:** [`tests/services/retrieval/test_trace_service.py`](../../tests/services/retrieval/test_trace_service.py), [`tests/services/retrieval/test_trace_integration.py`](../../tests/services/retrieval/test_trace_integration.py), and [`tests/models/test_retrieval_trace.py`](../../tests/models/test_retrieval_trace.py).
- **Design note:** [Retrieval Trace](../rag/retrieval-trace.md).

## 13. Evaluation Harness

- **Responsibility:** build temporary evaluation knowledge bases, run real retrieval through the service boundary, calculate deterministic evidence/citation/router metrics, and write reproducible reports.
- **Verified code paths:** [`scripts/eval/run_rag_generalization_eval.py`](../../scripts/eval/run_rag_generalization_eval.py), [`scripts/eval/rag_eval.py`](../../scripts/eval/rag_eval.py), [`tests/eval/rag_generalization_cases.jsonl`](../../tests/eval/rag_generalization_cases.jsonl), and [`tests/eval/corpus/`](../../tests/eval/corpus/).
- **Key entry points:** `run_generalization_cases()`, `load_cases()`, `evaluate_retrieval_result()`, `summarize_results()`, and `classify_failure_reasons()`.
- **What to look for:** answerable/no-answer denominators are explicit, expected and forbidden phrases replace LLM-as-judge, failed cases remain visible, and sanitized committed snapshots exclude live ids and secrets.
- **Related tests:** [`tests/eval/test_rag_eval_metrics.py`](../../tests/eval/test_rag_eval_metrics.py), [`tests/eval/test_generalization_case_quality.py`](../../tests/eval/test_generalization_case_quality.py), and [`tests/eval/test_rag_eval_baseline.py`](../../tests/eval/test_rag_eval_baseline.py).
- **Design note:** [RAG Evaluation](../rag/rag-evaluation.md) and the [latest committed baseline](../../tests/eval/baselines/answer-policy-auto-block-aware/summary.md).

## Continue with Design Deep Dives

The Code Tour is deliberately path-oriented. The [Technical Deep Dives](deep-dives/README.md) use these same verified entry points to explain request flow, document structure, routing and ranking, evidence/answer control, citation alignment, and evaluation failure analysis.
