# Final Portfolio Verification

## Scope and Baseline

Verified on 2026-10-06, starting from clean `main` at
`c25c7c30da7ec12909d1cc1a272da7e64f642e11`.
M4 was already committed and pushed as `feat: add public retrieval benchmark validation`;
it was reviewed rather than duplicated. Its focused provider/adapter tests passed
with **31 passed**. Closeout changes are documentation, ignore rules, and new
sanitized internal captures. Application code, Demo defaults, internal cases,
benchmark configurations, and historical snapshots remain unchanged.

The internal runners record `commit_sha=c25c7c3` and `dirty_worktree=true` because
documentation was being finalized. This metadata is preserved rather than
rewritten to suggest a clean historical run. Raw logs, generated documents, model
caches, and local results remain ignored under `data/eval_runs/portfolio-closeout/`.

## Tests and Documentation

| Exact command | Actual result |
|---|---|
| `make test-python` | **733 passed / 22 skipped**, 39.33 seconds |
| `make test-go` | Existing Go tests passed; three packages have no test files |
| `(cd frontend && PATH=/tmp/purelink-portfolio-tools/node_modules/node/bin:$PATH npm run lint)` | No ESLint warnings or errors |
| `(cd frontend && PATH=/tmp/purelink-portfolio-tools/node_modules/node/bin:$PATH npm run build)` | Compilation, type checks, and static-page build passed |
| `make docs-check` | 62 Markdown files checked; no broken relative links |
| `git diff --check` | Clean |

The backend used Python 3.12.3. All 22 skips are the explicit PureLink Core
exclusion of optional OCR/media extension coverage, not failures.
The host had Node 22, so frontend checks used isolated temporary **Node 24.21.0**,
matching the repository's supported Node major. The Docker build also used Node 24.
No frontend dependency or lockfile was changed for this environment adjustment.

The English README is within its 1,500–2,500 word target. Both READMEs have the
same major-section order, command/diagram blocks, numerical table values, and
local link targets. The existing citation/provenance screenshot remains the hero.

## Docker and Existing Smoke

Docker Desktop/WSL integration became available after the user restarted it.
Compose v5.1.2 was used. The existing customized `.env` was preserved; supplying
the example explicitly verifies the same default profile as a fresh Quick Start:
Chinese `BAAI/bge-small-zh-v1.5`, fixed chunking, heuristic answers, disabled/noop
reranking. No volume was reset.

```bash
docker compose --env-file .env.example up -d --build db redis api worker frontend
docker compose --env-file .env.example ps
docker compose --env-file .env.example exec -T db pg_isready -U purelink -d purelink
docker compose --env-file .env.example exec -T redis redis-cli ping
docker compose --env-file .env.example exec -T api alembic current
curl --noproxy '*' http://localhost:8000/api/v1/health
curl --noproxy '*' -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000
make KEEP_STACK_UP=1 COMPOSE='docker compose --env-file .env.example' smoke
```

Actual results: **db, redis, api, frontend healthy; Python worker running**.
PostgreSQL accepted connections, Redis returned `PONG`, PostgreSQL migration
revision was `20260525_0020 (head)`, API returned
`{"status":"ok","app":"PureLink","environment":"development"}`, and Web returned
HTTP 200. Startup's `upgrade head` path succeeded; a migration downgrade cycle
was not performed because no schema change is in this closeout.

The existing smoke returned **PASS: personal flow** with exit code 0. It covers
registration/login, KB creation, unsupported/empty upload rejection, TXT upload,
processing/index readiness, retrieval, QA, and persisted conversation messages.

## PDF Demo Rehearsal

The [Demo Guide](../interview/purelink-demo-guide.md) generates the existing
two-page `aspen-current.pdf` format fixture. A disposable local API rehearsal
uploaded it to a fresh KB and waited for readiness under the default Compose
profile: **2 chunks, 11 citation units**.

| Exact question | Verified response/provenance |
|---|---|
| How many days does the current Aspen runtime retain audit records? | 14 days; supporting citation has physical `page_number=2`, `page:2`, and PDF preview target; AUTO selected `chunk_only` |
| What is ASPEN_RETRY_LIMIT set to in the current Aspen runtime? | 6 retries; supporting citation points to page 1; AUTO selected `hybrid_text` |
| What is the release date of the Aspen runtime? | No-answer response, no citations |

All three responses record a retrieval trace ID. The authenticated original-file
endpoint returned HTTP 200 and `application/pdf`. The retention answer also
selected a page-1 introductory citation; this rehearsal does not claim perfect
evidence precision. The ignored rehearsal output contains no credentials or tokens.
Browser citation clicks and interactive drawer behavior were **not manually tested**;
the source/page contract was exercised through the API and frontend build.

## Final Internal Captures

```bash
make eval-rag-generalization GENERALIZATION_EVAL_OUTPUT_DIR=data/eval_runs/portfolio-closeout/internal EVAL_MODE=auto EVAL_CHUNK_STRATEGY=block_aware
make eval-rag-format FORMAT_EVAL_OUTPUT_DIR=data/eval_runs/portfolio-closeout/internal EVAL_MODE=auto EVAL_CHUNK_STRATEGY=block_aware
```

Both commands exited 0. They use `local_hashed_bow / hashed_bow_v1`, block-aware
chunking, AUTO routing, disabled/noop reranking, and min score .15. This deterministic
fixture profile differs from the normal Demo. Existing snapshot sanitization
produced new final captures without overwriting historical files.

| Metric | 50-case regression | 24-case format slice |
|---|---:|---:|
| Answerable / no-answer cases | 44 / 6 | 20 / 4 |
| Retrieval / citation hits | 43/44 / 43/44 | 20/20 / 20/20 |
| Expected evidence hits | 39/44 | 20/20 |
| Document Recall@1 / @3 / @5 | 79.5% / 93.2% / 97.7% | 85% / 100% / 100% |
| Document MRR | .8674 | .925 |
| Evidence recall | 79.2% | 100% |
| Evidence precision / applicable cases | 72.3% / 42 | 72.5% / 20 |
| Answerability | 49/50 | 24/24 |
| No-answer correctness | 6/6 | 4/4 |
| PDF page checks | N/A | 2/2 |
| Forbidden-evidence clean / applicable cases | 9/9 | 9/16 |

Compared with M4's retained internal captures, stage metrics and case-level
hits, forbidden labels, recalls, precision, ranking metrics, and failure stages
match. Run IDs/timing are fresh. See the final sanitized
[50-case summary](../../tests/eval/baselines/portfolio-final-auto-block-aware/summary.md)
and [24-case summary](../../tests/eval/baselines/portfolio-final-format-auto-block-aware/summary.md).
The [M2 → M3 ablation](../rag/evidence-selection-ablation.md) remains the historical
controlled experiment: precision 29.6% → 72.5%, recall 90% → 100%; coverage-only
was rejected after recall dropped to 80% despite higher apparent precision.

## Reused Public Validation

No provider/retrieval code changed after M4, so the six-task partial NanoBEIR
results were reused rather than rerunning the hour-long CPU comparison.
All three pipelines used the fixed English BGE quantized ONNX model, normalized
384-dimensional embeddings, top-k=10, and disabled reranking, across 300 queries.

| Pipeline | nDCG@10 | Recall@10 | MRR@10 |
|---|---:|---:|---:|
| MTEB Dense reference | .6222 | .6710 | .6821 |
| PureLink Dense | .6226 | .6710 | .6826 |
| PureLink Hybrid | .5569 | .6340 | .6055 |

Dense reference checks passed on all six tasks. Hybrid nDCG was lower on all six.
Seven tasks remain intentionally unrun at the user's runtime limit, and the
separate NanoSciFact smoke is excluded from these macro scores. See the
[public methodology and per-task results](../rag/rag-evaluation.md#public-retrieval-validation).
No full NanoBEIR result, leaderboard rank, or universal Hybrid benefit is claimed.

## Security Findings and Readiness

The additional read-only `(cd frontend && npm audit --json)` check exited 1:
**17 advisories, 2 moderate / 14 high / 1 critical**. Next.js 14.2.35 is among the
affected direct dependencies; npm's suggested fix includes a major Next.js
upgrade. No `audit fix --force`, dependency migration, or production-security
clearance was performed during this feature freeze. The audit JSON remains
ignored. These findings need remediation before public deployment.

**READY FOR INTERVIEW / PORTFOLIO** for the verified local demonstration and
engineering presentation. Required tests, build, documentation, Docker, smoke,
and internal evaluations completed. This recommendation does not claim safe
public deployment. Manual browser rehearsal, enterprise security audit,
production load testing, advanced PDF/OCR coverage, and the remaining seven
public tasks are outside the completed verification. Keep the remaining
[limitations](../interview/limitations.md) visible and retain the feature freeze.
