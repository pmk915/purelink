# PureLink Technical Deep Dives

These notes are for interviewers and engineers who want to examine the design decisions behind PureLink's document-to-answer path. They describe the current repository, including fallback behavior and limitations, rather than planned capabilities.

## Recommended Order

1. [Backend Request Flow](backend-request-flow.md): follow uploads and questions across API, service, worker, and response boundaries.
2. [Document Processing and Chunking](document-processing-and-chunking.md): understand parser routing, `DocumentBlock`, chunk strategies, and citation units.
3. [Retrieval Routing and Ranking](retrieval-routing-and-ranking.md): examine AUTO routing, candidate retrieval, graph augmentation, reranking, and trace data.
4. [Evidence, Answer Policy, and Citations](evidence-answer-and-citations.md): separate relevance, support, provider-call policy, marker validation, and citation serialization.
5. [Evaluation and Failure Analysis](evaluation-and-failure-analysis.md): interpret the committed 50-case deterministic baseline without overstating it.

## What Each Guide Answers

| Guide | Primary question |
|---|---|
| Backend Request Flow | Where does a request go, and which parts are shared? |
| Document Processing and Chunking | How does an upload become structure-preserving retrieval evidence? |
| Retrieval Routing and Ranking | How does PureLink choose and execute a retrieval mode? |
| Evidence, Answer Policy, and Citations | Why is retrieval not enough to permit an answer? |
| Evaluation and Failure Analysis | What has actually been measured, and where does it still fail? |

## Deep Dives vs Other Documentation

The [Code Tour](../code-tour.md) is a navigation map: it tells a reviewer where to open the implementation and tests. These Deep Dives explain why the boundaries exist, how data moves between them, and how to answer design follow-ups.

The [RAG architecture documentation](../../architecture/rag-v2-architecture.md) describes the system at a broader component level. These guides stay closer to verified functions, schemas, failure paths, and interview trade-offs.

## Time-boxed Reading

**Five minutes:** read the 30-second answer in [Backend Request Flow](backend-request-flow.md#30-second-interview-answer), then the decision model in [Evidence, Answer Policy, and Citations](evidence-answer-and-citations.md#30-second-interview-answer), and finish with the [baseline results](evaluation-and-failure-analysis.md#baseline-results).

**Fifteen minutes:** read the five guides in order, focusing on each flow diagram, comparison table, failure section, and known limitations. Use the linked [Code Tour](../code-tour.md) when an implementation detail needs direct verification.

