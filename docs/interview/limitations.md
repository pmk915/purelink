# PureLink: Scope and Limitations

PureLink is a feature-frozen, local-first/self-hosted RAG engineering workspace.
These boundaries describe the current implementation and measured results.

## Retrieval

The current production Hybrid path reduced nDCG@10 on all six evaluated public
NanoBEIR tasks. Lexical fusion is workload-dependent; its current scorer and
fusion weights were kept unchanged. Dense closely reproduced the independent
MTEB reference. This result does not establish behavior on unrun tasks or internal
evidence workloads.

AUTO uses deterministic rules. Its generalization has not been established on
a large public routing benchmark. Overview and graph candidates have bounded,
task-specific behavior. The PostgreSQL graph uses lightweight source-grounded
extraction and one-hop retrieval; it does not provide advanced multi-hop reasoning.
Reranking is optional and is not a central measured improvement in this portfolio.

## Evidence and Answers

The retained M3 change improves format-slice evidence precision to 72.5% and
recall to 100%, but seven cases still select explicitly forbidden evidence.
Archive facts, inseparable table rows, and cross-document noise remain. Query-term
coverage can miss paraphrases or compress distinct facts that share wording.

Support checks and Answer Policy use deterministic heuristics. They reject some
unsupported questions, but are not a semantic entailment proof. Backend markers
and source locators protect citation identity; a valid citation does not prove
every generated claim is correct. The default answer provider is heuristic.

## PDF

PyMuPDF extraction intentionally stays lightweight: page-aware ordered text
blocks, physical page numbers, bbox metadata, and citation provenance. Its
`sort=True` ordering does not guarantee correct multi-column reading order.
There is no advanced heading inference or dedicated table-structure model.
OCR is optional and disabled by default; scanned and mixed native/scanned
completeness is limited. Bboxes describe blocks, not exact sentence highlights.

## Evaluation

The internal 50-case and 24-case suites are small, deterministic engineering
tools. Phrase/document labels approximate evidence quality; unknown evidence
is excluded from precision, so applicability denominators matter. These metrics
do not mean production QA accuracy or semantic truth.

Public validation covers the first six of 13 predefined NanoBEIR tasks,
300 queries, one English quantized ONNX embedding model, CPU, and retrieval only.
Seven tasks were unrun at the user's runtime limit; the separate NanoSciFact
smoke is excluded from the macro. This is no full NanoBEIR or official leaderboard
result. It does not evaluate QA, citations, evidence selection, PDF, or AUTO routing.

## Operations and Production

There is no enterprise security audit or production-scale load benchmark.
The final frontend `npm audit` reported 17 advisories (2 moderate, 14 high,
1 critical). Suggested fixes include a major Next.js upgrade; dependency
remediation was not performed during this feature freeze. Build/smoke success
does not establish security clearance for public deployment.
Local vector artifacts, a local lexical scan, and the existing worker serve
the demonstrated scope. Authentication, ownership, membership, and review
boundaries are implemented; deployment still needs environment-specific TLS,
secrets, CORS, backups, upload controls, and database/cache isolation.

The supported Compose worker is Python. The experimental Go worker has different
capabilities and is not the default. Audio/video, general multimodal understanding,
billing, and enterprise administration are outside this Demo.

## Decision

Retain the measured evidence improvement and FastEmbed API correction, rebuild
existing FastEmbed indexes, preserve the Hybrid negative result, and freeze
feature work. Future questions are discussion material, not an active M5 plan.
See [Evaluation](../rag/rag-evaluation.md), [Ablation](../rag/evidence-selection-ablation.md),
and [Deployment](../development/docker-deployment.md) for the supporting detail.
