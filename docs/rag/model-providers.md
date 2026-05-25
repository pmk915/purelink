# Model Providers

PureLink separates model access from business logic through provider interfaces.

## EmbeddingProvider

Used by indexing and retrieval query embedding.

Implemented/default paths:

- `fastembed` with the configured local embedding model.
- `local_hashed_bow` deterministic fallback for tests and smoke.

Future-compatible paths are documented but not required by Core deployment.

## RerankerProvider

Used after initial retrieval when reranking is enabled.

Implemented:

- `noop`: default disabled behavior.
- `local_rule_reranker`: deterministic lexical reranker for development/tests.
- `flagembedding`: optional lazy provider when optional dependency is installed.

## LLMProvider

The provider interface exists for future migration. Current QA generation remains compatible with the existing answer generator path and configured `LLM_PROVIDER`.

## Accuracy Boundary

PureLink does not require heavy model downloads by default. Enhanced embedding/reranker providers are optional and should be enabled deliberately.
