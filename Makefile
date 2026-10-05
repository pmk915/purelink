SHELL := /usr/bin/env bash

COMPOSE ?= docker compose
GO ?= go
KEEP_STACK_UP ?= 0
EVAL_CASES ?= tests/eval/purelink_rag_cases.jsonl
EVAL_OUTPUT ?= tests/eval/reports/latest.json
EVAL_OUTPUT_DIR ?= data/eval_runs
LEGACY_EVAL_CASES ?= docs/interview/rag-eval-cases.json
LEGACY_EVAL_OUTPUT ?= docs/interview/rag-eval-baseline-results.json
LEGACY_EVAL_SUMMARY ?= docs/interview/rag-eval-baseline-summary.md
GENERALIZATION_EVAL_CASES ?= tests/eval/rag_generalization_cases.jsonl
GENERALIZATION_EVAL_OUTPUT_DIR ?= $(EVAL_OUTPUT_DIR)
FORMAT_EVAL_CASES ?= tests/eval/rag_format_cases.jsonl
FORMAT_EVAL_CORPUS_SPEC ?= tests/eval/format_corpus.json
FORMAT_EVAL_OUTPUT_DIR ?= $(EVAL_OUTPUT_DIR)
GENERALIZATION_HOLDOUT_CASES ?= tests/eval/rag_generalization_holdout_cases.jsonl
GENERALIZATION_HOLDOUT_CORPUS_DIR ?= tests/eval/holdout_corpus
GENERALIZATION_EVAL_SELECTED_CASES := $(if $(filter command line environment,$(origin EVAL_CASES)),$(EVAL_CASES),$(GENERALIZATION_EVAL_CASES))
GENERALIZATION_BASELINE_SNAPSHOT_DIR ?=
RUNTIME_EVAL_SNAPSHOT_DIR ?= tests/eval/baselines/runtime-fastembed-fixed
EVAL_MODE ?= auto
EVAL_CHUNK_STRATEGY ?= block_aware
PUBLIC_EVAL_MODES ?= official dense hybrid
PUBLIC_EVAL_OUTPUT_DIR ?= $(EVAL_OUTPUT_DIR)/external
PUBLIC_EVAL_BASELINE_SHA ?=
PUBLIC_EVAL_SMOKE ?= 0
PUBLIC_EVAL_TASK_LIMIT ?=

ifneq ("$(wildcard .venv/bin/python)","")
PYTHON ?= .venv/bin/python
else
PYTHON ?= python3
endif

.PHONY: up down logs ps build restart docker-up docker-down docker-logs docker-ps docker-smoke docker-prod-up docker-prod-down test test-python test-go check docs-check release-check smoke smoke-docx-rag e2e eval-rag eval-rag-legacy-20 eval-rag-generalization eval-rag-generalization-holdout eval-rag-format eval-rag-runtime

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f db redis api worker frontend

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

restart: down up

docker-up:
	$(COMPOSE) up --build -d db redis api worker frontend

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f db redis api worker frontend

docker-ps:
	$(COMPOSE) ps

docker-smoke:
	$(MAKE) smoke

docker-prod-up:
	$(COMPOSE) --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up --build -d db redis api worker frontend

docker-prod-down:
	$(COMPOSE) --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml down

test-python:
	$(PYTHON) -m pytest

test-go:
	cd worker-go && $(GO) test ./...

test: test-python test-go

check:
	scripts/check_stack.sh

docs-check:
	$(PYTHON) scripts/check_docs_links.py

release-check:
	$(MAKE) test
	cd frontend && npm run lint
	cd frontend && npm run build
	$(MAKE) docs-check

smoke:
	@set -euo pipefail; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	if [ "$(KEEP_STACK_UP)" != "1" ]; then trap '$(COMPOSE) down' EXIT; fi; \
	$(COMPOSE) up --build -d; \
	scripts/e2e/01_personal_flow.sh

smoke-docx-rag:
	$(PYTHON) scripts/smoke_docx_rag.py

eval-rag:
	$(PYTHON) scripts/eval/run_rag_eval.py --cases $(EVAL_CASES) --output $(EVAL_OUTPUT)

eval-rag-legacy-20:
	$(PYTHON) scripts/eval/run_rag_eval_baseline.py --cases $(LEGACY_EVAL_CASES) --output $(LEGACY_EVAL_OUTPUT) --summary $(LEGACY_EVAL_SUMMARY)

eval-rag-generalization:
	EVAL_MODE=$(EVAL_MODE) EVAL_CHUNK_STRATEGY=$(EVAL_CHUNK_STRATEGY) $(PYTHON) scripts/eval/run_rag_generalization_eval.py --cases $(GENERALIZATION_EVAL_SELECTED_CASES) --output-dir $(GENERALIZATION_EVAL_OUTPUT_DIR) --mode $(EVAL_MODE) --chunk-strategy $(EVAL_CHUNK_STRATEGY) $(if $(GENERALIZATION_BASELINE_SNAPSHOT_DIR),--baseline-snapshot-dir $(GENERALIZATION_BASELINE_SNAPSHOT_DIR),)

eval-rag-format:
	$(PYTHON) scripts/eval/run_rag_generalization_eval.py --suite format --cases $(FORMAT_EVAL_CASES) --corpus-spec $(FORMAT_EVAL_CORPUS_SPEC) --output-dir $(FORMAT_EVAL_OUTPUT_DIR) --mode $(EVAL_MODE) --chunk-strategy $(EVAL_CHUNK_STRATEGY)

eval-rag-generalization-holdout:
	EVAL_MODE=$(EVAL_MODE) EVAL_CHUNK_STRATEGY=$(EVAL_CHUNK_STRATEGY) $(PYTHON) scripts/eval/run_rag_generalization_eval.py --cases $(GENERALIZATION_HOLDOUT_CASES) --corpus-dir $(GENERALIZATION_HOLDOUT_CORPUS_DIR) --output-dir $(GENERALIZATION_EVAL_OUTPUT_DIR) --mode $(EVAL_MODE) --chunk-strategy $(EVAL_CHUNK_STRATEGY)

eval-rag-runtime:
	$(PYTHON) scripts/eval/run_rag_generalization_eval.py --cases $(GENERALIZATION_EVAL_CASES) --output-dir $(GENERALIZATION_EVAL_OUTPUT_DIR) --baseline-snapshot-dir $(RUNTIME_EVAL_SNAPSHOT_DIR) --mode auto --chunk-strategy fixed --embedding-provider fastembed --embedding-model BAAI/bge-small-zh-v1.5 --no-reranker-enabled --reranker-provider noop

.PHONY: eval-retrieval-nanobeir
eval-retrieval-nanobeir:
	$(PYTHON) -B scripts/eval/run_public_retrieval.py --modes $(PUBLIC_EVAL_MODES) --output-dir $(PUBLIC_EVAL_OUTPUT_DIR) $(if $(filter 1,$(PUBLIC_EVAL_SMOKE)),--smoke,) $(if $(PUBLIC_EVAL_BASELINE_SHA),--baseline-sha $(PUBLIC_EVAL_BASELINE_SHA),) $(if $(PUBLIC_EVAL_TASK_LIMIT),--task-limit $(PUBLIC_EVAL_TASK_LIMIT),)

e2e:
	@set -euo pipefail; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	if [ "$(KEEP_STACK_UP)" != "1" ]; then trap '$(COMPOSE) down' EXIT; fi; \
	$(COMPOSE) up --build -d; \
	scripts/e2e/run_all.sh
