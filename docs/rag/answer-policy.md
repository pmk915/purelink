# Answer Policy Contract

PureLink applies Answer Policy after final evidence selection and the Evidence
Support Gate:

```text
RetrievalResult.evidences
  -> Evidence Support Gate
  -> Answer Policy
  -> answer provider or refusal
  -> marker validation
  -> citation-aligned answer
```

## Responsibilities

The Support Gate decides whether the selected evidence supports the current
question. Answer Policy then decides whether an answer provider may run, which
evidence markers it may use, and whether citations are required. Answer Policy
does not change the requested, selected, or effective retrieval mode.

An answer is allowed only when the Support Gate accepts the evidence, the
retrieval context is reliable, final evidence is present, and every final
evidence unit is citation-ready. Mixed ready and non-ready final evidence is
refused so that the Support Gate, provider context, marker validation, and
citations stay aligned. External knowledge is disabled. The heuristic provider
and OpenAI-compatible providers receive the same evidence-only instructions and
the same allowed marker list.

A refusal uses the existing insufficient-evidence message, does not call the
provider, and returns no citations. Provider failures continue to use the
existing error path; PureLink does not replace them with a fabricated answer.

## Evidence And Citations

`RetrievalResult.evidences` remains the canonical source for provider context
and citations. Conversation history can clarify references in the current
question, but it is not document evidence and cannot become a citation source.

Provider markers are normalized against the allowed final-evidence markers.
Unknown markers are removed, duplicate citations are deduplicated, and citation
order follows the first valid reference in the answer. Evidence that the
provider does not reference is not attached automatically. If no valid marker
remains, the generated text is rejected and the response becomes a refusal.

Citation Readiness and Answer Policy solve different problems. Citation
Readiness verifies that an evidence unit has persisted provenance, including a
citation unit id and source locator. Answer Policy decides whether that ready,
supported evidence may be sent to an answer provider.

## Trace Metadata

Retrieval trace JSON records the internal decision without changing the public
ask response schema:

- `answer_policy_outcome`
- `answer_policy_reason`
- `answer_provider_called`
- `answer_citation_required`
- `answer_external_knowledge_allowed`
- `answer_allowed_evidence_count`
- `answer_allowed_markers`
- `answer_unknown_markers_removed`

## Current Boundary

The internal outcome type reserves `answer_with_limitations` and
`present_conflict`, but M27B1 does not infer either state from wording,
different numbers, or multiple documents. Reliable partial-answer and conflict
detection require explicit structured signals and remain future work.
