# PureLink 5-Minute Interview Demo

## Goal

Demonstrate one engineering story:

```text
Structured Ingestion
→ Routed Retrieval
→ Evidence Selection
→ Evidence Support
→ Answer Policy
→ Backend-grounded Citations
→ Retrieval Trace / Evaluation
```

PureLink is an engineering-focused RAG knowledge workspace. The main demo is deliberately limited to five steps; supporting features are available only for follow-up questions.

## Before the Interview

```bash
cp .env.example .env
docker compose up -d --build db redis api worker frontend
docker compose ps
```

Open `http://localhost:3000`, register a local user, and create a personal knowledge base. Use a real text document that contains the `CHUNK_STRATEGY`, `fixed`, and `block_aware` terms; [`docs/ingestion/document-blocks.md`](../ingestion/document-blocks.md) is suitable. Keep a second unsupported question ready whose answer is absent from the uploaded corpus.

## Main Flow

### Step 1 — Upload

Upload the document and show the processing transition:

```text
processing → blocks → chunks → citation units → index
```

Say: “The system persists a parser-neutral `DocumentBlock` representation, then creates retrieval chunks and smaller citation units. Parsing policy can evolve separately from chunking and citation policy.”

Trade-off: structured ingestion creates more rows and processing stages than flattening every file into one text stream.

### Step 2 — Document Processing Inspector

Open the document inspector and show:

- RAG Ready
- block count
- chunk count
- citation-unit count
- vector index
- graph index

Say: “A user should not need worker logs to learn why a file is not searchable. Readiness and failure states are product-visible.”

### Step 3 — Technical Question and Citations

Ask:

```text
CHUNK_STRATEGY 支持哪些值？
```

Show `AUTO → hybrid_text`, the grounded answer, inline markers, and Citation Drawer.

Say: “Semantic embeddings are not ideal for config keys, API paths, and CLI commands. The keyword channel adds observable exact-match candidates; the trade-off is a simple local scan rather than a production inverted index. Citation identities come from the backend, and provider markers are validated after generation.”

### Step 4 — Retrieval Trace

Show:

- requested, selected, and effective mode
- router reason
- candidate and final-evidence scores
- trace id
- Evidence Support and Answer Policy metadata

Say: “When an answer fails, I need to distinguish routing, retrieval, selection, evidence support, and answer-policy failures. A deterministic rule router is sufficient for this small explicit strategy space; an LLM router would add latency, cost, and nondeterminism.”

### Step 5 — Unsupported Question

Ask a question whose requested fact is absent from the uploaded corpus, for example a nonexistent author or default value.

Show:

```text
Evidence Support rejects
→ Answer Policy refuses
→ provider skipped
→ citations=[]
```

Say: “Retrieved relevance is not answerability. Semantically related evidence can still lack the requested fact, so generation is gated before the model sees context.”

## Evaluation Talking Point

The only current official regression suite is the [50-case deterministic generalization baseline](../../tests/eval/baselines/answer-policy-auto-block-aware/summary.md):

```bash
make eval-rag-generalization
make eval-rag-generalization-holdout
```

The [default Runtime snapshot](../../tests/eval/baselines/runtime-fastembed-fixed/summary.md) uses the same 50 cases with fixed chunking and FastEmbed:

```bash
make eval-rag-runtime
```

Frame them separately: deterministic evaluation detects regression; runtime evaluation describes the actual Demo defaults. Neither is an LLM-judge benchmark or a production-quality claim.

## Optional / Follow-up Demo

Only show these when the interviewer asks:

- Graph Explorer and one-hop source provenance
- team knowledge bases and review permissions
- Processing Job Dashboard and retry
- manual retrieval modes
- optional reranker
- graph lifecycle and export
- production-like Docker Compose setup

The graph is lightweight, one-hop/source-grounded, and PostgreSQL-backed. It is not multi-hop GraphRAG or a Neo4j-style analytics platform. The Python worker is the supported Compose path; `worker-go` is experimental and not feature-equivalent.

## Honest Limits

- The corpus is small and phrase/document metrics approximate evidence quality.
- The rule-based router and Evidence Support Gate are deterministic heuristics.
- Default FastEmbed still has expected-evidence and answerability failures recorded in its snapshot.
- OCR, multimodal RAG, agent runtime, and multi-hop graph reasoning are outside the final Demo scope.
- Public production deployment still needs environment-specific TLS, secrets, monitoring, backups, and capacity work.

## Troubleshooting

If a document is not ready, use the inspector before logs. If retrieval is surprising, check selected mode, trace id, candidate/final evidence, support reason, and index-provider compatibility. Docker commands:

```bash
docker compose logs --tail=200 api worker
docker compose ps
```
