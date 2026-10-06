# Model Providers

PureLink separates model access from business logic through provider interfaces.

## EmbeddingProvider

Used by indexing and retrieval query embedding.

Implemented/default paths:

- `fastembed` with the configured local embedding model.
- `local_hashed_bow` deterministic fallback for tests and smoke.

The normal Demo defaults to FastEmbed / BAAI/bge-small-zh-v1.5; first use can
download model weights. M4 delegates to model-native query_embed()/passage_embed()
where available; older implementations fall back narrowly to embed() with raw
text. It does not add generic query:/passage: instructions. Existing FastEmbed
indexes require a complete rebuild after this change. The separate public
benchmark uses the explicit English profile; application defaults are unchanged.

Future-compatible paths are documented but not required by Core deployment.

## RerankerProvider

Used after initial retrieval when reranking is enabled.

Implemented:

- `noop`: default disabled behavior.
- `local_rule_reranker`: deterministic lexical reranker for development/tests.
- `flagembedding`: optional lazy provider when optional dependency is installed.

## LLMProvider

QA uses the existing answer-generator path and configured `LLM_PROVIDER`.
The default heuristic path needs no external key; optional OpenAI-compatible
providers require their own configuration. Evidence Support and Answer Policy
decide whether a provider is called before generation.

## Accuracy Boundary

The Demo's local embedding model may download on first use. Optional rerankers
and external answer providers are enabled deliberately. Internal hashed-BOW
regression needs no downloaded embedding model. Public MTEB dependencies are
development-only; see [Evaluation](rag-evaluation.md#public-retrieval-validation).
