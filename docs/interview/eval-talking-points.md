# RAG Eval Talking Points

## 1. Why Evaluation Was Added

PureLink added eval because RAG changes are otherwise too easy to discuss only by anecdote. The goal is not to claim a statistically complete benchmark. The goal is to make retrieval and citation changes repeatable enough to catch regressions and explain tradeoffs.

The eval baseline helps answer:

- Did the expected source document appear in retrieved evidence?
- Did citation-ready evidence include the expected source?
- Did the expected source appear near the top?
- Did retrieved context cover the expected keywords?
- Was a retrieval trace recorded?
- When `auto` was requested, which concrete mode did the router select?

## 2. Dataset

The current baseline uses 20 repository-doc cases from [rag-eval-cases.json](rag-eval-cases.json).

Case types:

- overview: 4
- technical: 6
- relation: 5
- factual: 5

The cases are based on PureLink's own documentation, including retrieval, ingestion, GraphRAG, product workspace, eval, and smoke docs. This makes the baseline easy to reproduce locally and useful for interview demos.

## 3. Compared Baselines

The runner compares:

- `fixed + chunk_only`
- `block_aware + chunk_only`
- `block_aware + hybrid_text`
- `block_aware + graph_vector_mix`
- `block_aware + auto`

Fixed and block-aware chunking are compared by rebuilding separate temporary KBs because chunk strategy is decided during ingestion.

## 4. Metrics

- `retrieval_hit`: final retrieved evidence includes the expected source document.
- `citation_hit`: citation-ready evidence includes the expected source document.
- `top_1_doc_hit`: expected source is the first final evidence document.
- `top_3_doc_hit`: expected source appears in the first three final evidence documents.
- `keyword_coverage`: fraction of expected keywords found in retrieved context.
- `trace_available`: retrieval wrote a trace id.
- `selected_mode`: actual retrieval mode used. For `auto`, this is selected by the Query Router.
- `router_reason`: rule-based explanation for `auto`.
- `answer_contains_expected`: currently not calculated because this baseline evaluates retrieval and citation evidence, not generated answers.

## 5. Current Results

Current generated summary: [rag-eval-baseline-summary.md](rag-eval-baseline-summary.md).

| Baseline | retrieval_hit | citation_hit | top_1_doc_hit | top_3_doc_hit | keyword_coverage | trace_available |
|---|---:|---:|---:|---:|---:|---:|
| `fixed_chunk_only` | 50.0% | 50.0% | 20.0% | 25.0% | 29.3% | 100.0% |
| `block_aware_chunk_only` | 65.0% | 65.0% | 35.0% | 45.0% | 27.7% | 100.0% |
| `block_aware_hybrid_text` | 55.0% | 55.0% | 20.0% | 40.0% | 21.7% | 100.0% |
| `block_aware_graph_vector_mix` | 30.0% | 30.0% | 15.0% | 20.0% | 20.0% | 100.0% |
| `block_aware_auto` | 45.0% | 45.0% | 25.0% | 40.0% | 21.4% | 100.0% |

Auto selected modes in the current run:

- `chunk_only`: 7
- `graph_vector_mix`: 5
- `hybrid_text`: 6
- `overview`: 2

## 6. Honest Findings

Block-aware chunking is the clearest current win:

- `block_aware_chunk_only` improved retrieval_hit and citation_hit by +15.0 percentage points compared with `fixed_chunk_only`.
- It also improved top-1 and top-3 document hit rates in the current run.
- Keyword coverage is slightly lower than `fixed_chunk_only` in the current run, so do not describe block-aware as improving every metric.

Hybrid text is useful, but not globally better:

- Overall, `block_aware_hybrid_text` is below `block_aware_chunk_only` in retrieval_hit and citation_hit in the current run.
- For technical/API/config cases, it produced 66.7% retrieval_hit and 66.7% citation_hit.
- The correct framing is that `hybrid_text` is a targeted mode for exact technical tokens, not a universal replacement for vector retrieval.

Graph vector mix is currently limited on this docs corpus:

- `block_aware_graph_vector_mix` produced 30.0% retrieval_hit and 30.0% citation_hit overall.
- For relation/dependency cases, it produced 20.0% retrieval_hit, 20.0% citation_hit, and 30.0% keyword coverage.
- The honest takeaway is that the current lightweight local-rule graph helps expose provenance and graph debugging, but it is not yet a strong global retrieval winner.

Auto router improves ergonomics and observability, not global optimality:

- `block_aware_auto` records selected modes and router reasons.
- It helps users avoid manually selecting modes.
- It is still rule-based and does not guarantee the best baseline score for every query.
- In the current run, `block_aware_auto` produced 45.0% retrieval_hit and 45.0% citation_hit overall.

Trace availability is stable:

- All current baselines report 100.0% trace availability.
- This is important for debugging because every eval case can be inspected through trace metadata.

## 7. How This Guides Next Iteration

The eval points to specific next work:

- Expand the eval dataset beyond repository docs before claiming broad quality improvements.
- Add more technical cases to test `hybrid_text` where it should win.
- Improve graph extraction quality before expecting `graph_vector_mix` to outperform vector retrieval.
- Add answer-level evaluation only after retrieval/citation metrics are stable.
- Keep `auto` explanations visible so routing mistakes can become test cases.

## 8. Reproduction Command

```bash
make eval-rag-baseline
```

Equivalent direct command:

```bash
.venv/bin/python scripts/eval/run_rag_eval_baseline.py \
  --cases docs/interview/rag-eval-cases.json \
  --output docs/interview/rag-eval-baseline-results.json \
  --summary docs/interview/rag-eval-baseline-summary.md
```

The baseline can change slightly when documentation content changes, because repository docs are the eval corpus.
