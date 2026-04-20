SHELL := /usr/bin/env bash

COMPOSE ?= docker compose
GO ?= go
KEEP_STACK_UP ?= 0

ifneq ("$(wildcard .venv/bin/python)","")
PYTHON ?= .venv/bin/python
else
PYTHON ?= python3
endif

.PHONY: up down logs ps build restart test test-python test-go smoke e2e

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f db api worker

ps:
	$(COMPOSE) ps

build:
	$(COMPOSE) build

restart: down up

test-python:
	$(PYTHON) -m pytest

test-go:
	cd worker-go && $(GO) test ./...

test: test-python test-go

smoke:
	@set -euo pipefail; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	if [ "$(KEEP_STACK_UP)" != "1" ]; then trap '$(COMPOSE) down' EXIT; fi; \
	$(COMPOSE) up --build -d; \
	scripts/e2e/01_personal_flow.sh

e2e:
	@set -euo pipefail; \
	if [ ! -f .env ]; then cp .env.example .env; fi; \
	if [ "$(KEEP_STACK_UP)" != "1" ]; then trap '$(COMPOSE) down' EXIT; fi; \
	$(COMPOSE) up --build -d; \
	scripts/e2e/run_all.sh
