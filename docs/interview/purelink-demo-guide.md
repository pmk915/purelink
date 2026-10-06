# PureLink 3–5 Minute Interview Demo

## Prepare Before Presenting

Use the default Chinese FastEmbed model, fixed chunking, heuristic answer
provider, and disabled/noop reranking. Model download and indexing happen before
the live demo. Keep existing environment files when they contain local settings;
copy the example only in a fresh checkout.

```bash
cp .env.example .env
docker compose up -d --build db redis api worker frontend
docker compose ps
curl --noproxy '*' http://localhost:8000/api/v1/health
```

Expect db, redis, api, and frontend healthy; worker running. A created container
alone does not establish readiness. If .env is already customized, use
`docker compose --env-file .env.example up -d --build db redis api worker frontend`
to rehearse the documented defaults without overwriting it.

Generate the **existing** format benchmark fixtures locally; this adds no dataset
and commits no generated PDF/DOCX. Install the existing Python requirements in a
local Python 3.12 virtualenv first (see [development setup](../development/dev-commands.md)).

```bash
.venv/bin/python - <<'PYDEMO'
from pathlib import Path
from scripts.eval.rag_eval import load_cases
from scripts.eval.rag_format import generate_format_corpus
generate_format_corpus(
    Path("tests/eval/format_corpus.json"),
    Path("data/demo/format-corpus"),
    load_cases(Path("tests/eval/rag_format_cases.jsonl")),
)
print("Upload data/demo/format-corpus/aspen-current.pdf")
PYDEMO
```

`aspen-current.pdf` has two native-text pages. Page 1 states the retry limit (6);
page 2 states audit retention (14 days) and profile memory. These are synthetic
runtime facts already used by the internal benchmark. Upload only this current
PDF to a fresh demo KB; do not introduce archive distractors in the live flow.
`examples/pdf/manual.pdf` is a single-page alternative and cannot demonstrate
page-2 provenance.

## 0:00–1:00 — Sign In, Upload, and Readiness

Open http://localhost:3000. Register/sign in, create a personal knowledge base,
and upload `aspen-current.pdf`. Wait for indexed/RAG Ready; use the Processing
Inspector to show blocks, chunks, citation units, and vector-index readiness.
Uploads are prepared asynchronously; the manual processing action is available
if an existing document is not queued. Pre-create an indexed KB as a fallback.

Say: “Parsing preserves physical PDF pages and source blocks. Retrieval uses
chunks, while answer evidence uses smaller citation units with provenance.”

## 1:00–2:00 — Stable Question and Supported Answer

Ask in AUTO mode:

```text
How many days does the current Aspen runtime retain audit records?
```

The source fact is **14 days** on **physical page 2**. Show the grounded answer,
its inline citation, and the supporting quote. Do not promise an exact answer
sentence, fixed marker number, score, latency, or AUTO mode for this generic query.
An optional technical question is:

```text
What is ASPEN_RETRY_LIMIT set to in the current Aspen runtime?
```

The source fact is **6 retries**, page 1. Inspect the actual route rather than
claiming Hybrid must win. If the first question is unsupported in an unexpected
runtime, inspect readiness and trace; use the rehearsed second question or the
pre-indexed KB, and disclose the failed attempt.

## 2:00–3:00 — Click Citation and Inspect Decisions

Open the citation drawer. Show `source_type=pdf`, physical page 2, source locator,
quote, and character range; open View source. Physical pages do not mean printed
page labels, and bbox is block metadata rather than a sentence-highlight promise.

Expand Retrieval Details / Retrieval Debug. Show the actual requested, selected,
and effective modes, router reason, trace id, scored candidates, final evidence,
and support/Answer Policy decision. UI summaries and persisted backend trace can
expose different levels of detail; do not invent fields that are not displayed.

Say: “A related candidate can be retrieved without becoming final evidence.
The support decision gates generation, and citations come from backend evidence.”

## 3:00–4:00 — Optional Refusal and Evaluation

If time permits, ask a fact absent from the PDF:

```text
What is the release date of the Aspen runtime?
```

Check the actual no-answer decision: unsupported evidence, provider skipped,
and no citations. Finish with the README's three evaluation stories: the 50-case
regression, the retained/rejected evidence ablation, and the six-task partial
NanoBEIR Dense/Hybrid result. Never start the hour-long public run during a demo.

## Rehearsal and Troubleshooting

The final closeout rehearsed these exact questions through the local API with
the default Compose profile: 14 days/page 2, 6 retries/page 1, and a no-citation
refusal all passed. The PDF produced 2 chunks and 11 citation units, and its
authenticated original source returned HTTP 200. This verifies the backend
contract; browser clicks still require presenter rehearsal. See the
[actual verification record](../development/portfolio-verification.md).

```bash
make KEEP_STACK_UP=1 smoke
make eval-rag-generalization GENERALIZATION_EVAL_OUTPUT_DIR=data/eval_runs/demo-rehearsal
make eval-rag-format FORMAT_EVAL_OUTPUT_DIR=data/eval_runs/demo-rehearsal
docker compose logs --tail=100 api worker
```

Smoke exercises the existing personal upload/retrieve/ask/conversation path;
it does not replace the PDF page check. Generated runs stay ignored. Do not run
`make eval-rag-runtime` to capture fresh measurements without understanding that
it overwrites the historical runtime snapshot; use the runner directly without
`--baseline-snapshot-dir` as documented in [Evaluation](../rag/rag-evaluation.md).
Existing FastEmbed indexes must be fully rebuilt after M4's API correction.

Graph Explorer, teams/review, manual retrieval modes, jobs/retry, and optional
rerankers are follow-up material. The Compose worker is Python; worker-go is
experimental. Explain [limitations](limitations.md) confidently and factually.
