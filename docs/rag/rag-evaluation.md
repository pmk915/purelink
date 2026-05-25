# RAG Evaluation

PureLink includes a lightweight JSONL evaluation harness.

Runner:

```bash
make eval-rag
```

Custom cases:

```bash
make eval-rag EVAL_CASES=tests/eval/purelink_rag_interview_cases.local.jsonl
```

## Case Format

Each JSONL line includes:

- `id`
- `question`
- `knowledge_base_id`
- `user_id`
- `mode`
- `top_k`
- `expected_doc_names`
- `expected_keywords`
- `expected_citation_required`

## Metrics

- `retrieval_hit`: expected document appears in final evidence.
- `citation_hit`: citation-ready evidence appears from expected document.
- `keyword_coverage`: expected keyword substring coverage in context.
- `top_1_doc_hit` / `top_3_doc_hit`: ranking quality indicators.
- `used_reranker`: whether reranker changed the pipeline.
- `trace_available`: whether retrieval produced a trace id.

The harness is deterministic and does not use LLM-as-judge.

Supported modes include:

- `chunk_only`
- `overview`
- `graph_vector_mix`
- `hybrid_text`

Use `hybrid_text` cases for keyword-heavy questions about API paths, config keys, file paths, commands, migration ids, or error codes.

## Comparing Chunk Strategies

To compare fixed and block-aware chunking:

1. Set `CHUNK_STRATEGY=fixed`.
2. Reindex the target documents.
3. Run eval and save the report.
4. Set `CHUNK_STRATEGY=block_aware`.
5. Reindex the same documents.
6. Run eval again.
7. Compare `retrieval_hit`, `citation_hit`, `keyword_coverage`, and `top_1_doc_hit` / `top_3_doc_hit`.

Block-aware chunking should be evaluated empirically. It preserves document structure better, but it is not expected to improve every case.

## Comparing Retrieval Modes

The same JSONL case set can be run with different modes to compare recall behavior:

1. Run with `mode=chunk_only`.
2. Run with `mode=hybrid_text`.
3. Compare `retrieval_hit`, `citation_hit`, `keyword_coverage`, and top-k document hits.

`hybrid_text` is expected to help exact technical queries. It should not be assumed to improve every semantic question.
