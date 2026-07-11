SHELL := /usr/bin/env bash

COMPOSE ?= docker compose
GO ?= go
KEEP_STACK_UP ?= 0
EVAL_CASES ?= tests/eval/purelink_rag_cases.jsonl
EVAL_OUTPUT ?= tests/eval/reports/latest.json
EVAL_OUTPUT_DIR ?= data/eval_runs
BASELINE_EVAL_CASES ?= docs/interview/rag-eval-cases.json
BASELINE_EVAL_OUTPUT ?= docs/interview/rag-eval-baseline-results.json
BASELINE_EVAL_SUMMARY ?= docs/interview/rag-eval-baseline-summary.md
GENERALIZATION_EVAL_CASES ?= tests/eval/rag_generalization_cases.jsonl
GENERALIZATION_EVAL_OUTPUT_DIR ?= $(EVAL_OUTPUT_DIR)
GENERALIZATION_EVAL_SELECTED_CASES := $(if $(filter command line environment,$(origin EVAL_CASES)),$(EVAL_CASES),$(GENERALIZATION_EVAL_CASES))
GENERALIZATION_BASELINE_SNAPSHOT_DIR ?=
EVAL_MODE ?= auto
EVAL_CHUNK_STRATEGY ?= block_aware

ifneq ("$(wildcard .venv/bin/python)","")
PYTHON ?= .venv/bin/python
else
PYTHON ?= python3
endif

.PHONY: up down logs ps build restart docker-up docker-down docker-logs docker-ps docker-smoke docker-prod-up docker-prod-down test test-python test-go check docs-check release-check smoke smoke-docx-rag e2e eval-rag eval-rag-baseline eval-rag-generalization

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

eval-rag-baseline:
	$(PYTHON) scripts/eval/run_rag_eval_baseline.py --cases $(BASELINE_EVAL_CASES) --output $(BASELINE_EVAL_OUTPUT) --summary $(BASELINE_EVAL_SUMMARY)

eval-rag-generalization:
	EVAL_MODE=$(EVAL_MODE) EVAL_CHUNK_STRATEGY=$(EVAL_CHUNK_STRATEGY) $(PYTHON) scripts/eval/run_rag_generalization_eval.py --cases $(GENERALIZATION_EVAL_SELECTED_CASES) --output-dir $(GENERALIZATION_EVAL_OUTPUT_DIR) --mode $(EVAL_MODE) --chunk-strategy $(EVAL_CHUNK_STRATEGY) $(if $(GENERALIZATION_BASELINE_SNAPSHOT_DIR),--baseline-snapshot-dir $(GENERALIZATION_BASELINE_SNAPSHOT_DIR),)

e2e:
	@set -euo pipefail; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	if [ "$(KEEP_STACK_UP)" != "1" ]; then trap '$(COMPOSE) down' EXIT; fi; \
	$(COMPOSE) up --build -d; \
	scripts/e2e/run_all.sh
