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
