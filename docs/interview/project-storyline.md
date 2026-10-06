# PureLink: a Five-minute Project Story

Use this as a hypothesis → measurement → finding → engineering decision talk track.
The project is feature-frozen. The [README](../../README.md) is the public summary;
[Evaluation](../rag/rag-evaluation.md) owns detailed definitions and results.

## 0:00–0:40 — Problem and Architecture

“I built a local-first RAG knowledge workspace because I wanted to inspect why
an answer is supported. Finding a relevant document alone does not show that the
selected text contains the requested fact.”

Next.js talks to FastAPI. PostgreSQL stores users, KBs, blocks, chunks, citation
units, jobs, and traces. Redis queues work for the Python processing worker.
Local embedding/index services support the default self-hosted path. The Go
worker is experimental and does not replace the Compose worker.

Ingestion separates parser output from chunking: TXT/Markdown/DOCX/native-text
PDF → DocumentBlock → chunks → citation units. Chunks supply retrieval context;
citation units supply narrower evidence with source ranges and physical pages.
M1 added ordered PyMuPDF blocks and bbox metadata without a layout-AI framework.

## 0:40–1:20 — Retrieval Hypothesis

“My hypothesis was that exposing several candidate strategies would make
technical and factual queries easier to diagnose. I implemented dense, keyword,
overview, and lightweight graph candidates behind a rule-based AUTO router.”

Technical keys and paths motivate a lexical channel; relation questions motivate
source-grounded graph candidates. These are hypotheses, not guarantees of
quality. Requested, selected, and effective modes, router reasons, candidate
scores, and selected evidence appear in Retrieval Trace. Readiness diagnostics
explain why a document is not searchable before reading worker logs.

## 1:20–2:10 — Measurement Revealed an Evidence Bottleneck

“The separate 24-case format benchmark had 100% document Recall@5 and .925 MRR,
but final-evidence precision was only 29.6% and evidence recall 90%. Candidate
documents were already present. The loss occurred while selecting final evidence.”

The slice has six cases per format, 20 answerable questions, four no-answer
questions, and current/archive distractors. Evidence metrics are deterministic
phrase proxies. Unknown evidence is excluded from precision; I report its
applicability denominator together with recall.

This differs from the 50-case regression: 44 answerable plus six no-answer cases,
retrieval/citation 43/44, expected evidence 39/44, answerability 49/50. That suite
checks behavioral stability; it is not a public or production benchmark.

## 2:10–3:10 — Controlled Improvement and Rejected Variant

“M3 selected generic evidence by incremental meaningful query-term coverage.
A separately identified responsibility-matching fix handled active/passive
maintainer wording and entity binding. I measured the selector-only variant
and the combined change, keeping corpus, ranking, embedding, chunking, and
Answer Policy fixed.”

Coverage-only appeared to improve precision to 78.1% on 16 applicable cases,
but evidence recall fell to 80%. I rejected it. The retained combined change
reached 72.5% precision on 20 applicable cases and 100% evidence recall;
expected evidence rose 18/20 → 20/20 and answerability 20/24 → 24/24.
Recall@5, MRR, no-answer 4/4, and physical PDF page checks 2/2 were preserved.
The 50-case metrics, failure stages, and evidence counts remained unchanged.

Seven format cases still select forbidden evidence. Archive facts, inseparable
table rows, and cross-document noise remain. The improvement is useful within
these small fixtures; it does not prove semantic answer correctness.

## 3:10–4:10 — Public Reference and Hybrid Negative Result

“I wanted an external retrieval reference beyond self-built fixtures. M4 first
corrected FastEmbed to use model-native query_embed()/passage_embed(), then
compared independent official MTEB search with PureLink production retrieval.”

The English experiment fixed BAAI/bge-small-en-v1.5, quantized ONNX, 384 normalized
dimensions, CPU, top-k=10, official title/text and qrels, with reranking disabled.
The user limited runtime to the first six predefined NanoBEIR tasks (300 queries).
Seven tasks are explicitly unrun; the separate NanoSciFact smoke is excluded.

Macro nDCG@10 is .6222 for the MTEB reference, .6226 for PureLink Dense, and
.5569 for production Hybrid. All Dense reference checks passed. Hybrid reduced
nDCG on all six tasks. I kept the result and did not tune those tasks to win.
This validates the Dense plumbing and shows that the current fusion is
workload-dependent. It gives neither a full NanoBEIR result nor a leaderboard rank.

The FastEmbed correction is retained, with a required complete rebuild of
existing FastEmbed indexes. Provider-only runtime Recall@3 changed 100% → 97.7%
and MRR .9318 → .925; hits and answerability did not change. Historical snapshots
are preserved and these differences are disclosed.

## 4:10–5:00 — Decision, Limits, and Next Steps

“Candidate retrieval, final evidence, support, answer policy, and citations are
separate engineering decisions. The project value is being able to locate a
failure, test a hypothesis, reject an attractive but lossy experiment, and
retain a negative public result.”

The support gate and router are heuristics. Native PDF extraction does not
solve multi-column layout, heading inference, structured tables, or complete
OCR-heavy ingestion. There is no enterprise security audit or production-scale
load benchmark. See [Limitations](limitations.md).

The decision is feature freeze: preserve results, document reproduction, and
prepare the [3–5 minute demo](purelink-demo-guide.md). Future research directions
can be discussed as unimplemented hypotheses; no M5, reranker, router learning,
new dataset, or retrieval tuning is part of this closeout.
