# VGB KYC review workflow: prototype
#
# `make` or `make help` lists the targets. Every target runs through uv, so
# nothing here needs an activated virtualenv.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Settings the services read from the environment.
# Override on the command line: `make up VGB_PORT=8010 MCP_PORT=8011`.
VGB_PORT ?= 8000
VGB_API_KEY ?= vgb-demo-key
VGB_DATA_DIR ?= $(CURDIR)/data
MCP_PORT ?= 8001
UI_PORT ?= 8002
RUN_DIR := $(CURDIR)/.run

export VGB_PORT VGB_API_KEY VGB_DATA_DIR MCP_PORT UI_PORT

.PHONY: help up down restart status bank-api bank-api-check mcp mcp-tools ui test test-live ping chat pack eval-routing eval-guardrails eval-pack

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Variables: VGB_PORT=$(VGB_PORT)  MCP_PORT=$(MCP_PORT)  UI_PORT=$(UI_PORT)  VGB_API_KEY=$(VGB_API_KEY)  VGB_DATA_DIR=$(VGB_DATA_DIR)"

up: ## Start the bank API, the MCP server (HTTP) and the UI in the background; logs and pids in .run/
	@mkdir -p $(RUN_DIR)
	@if [ -f $(RUN_DIR)/bank-api.pid ] && kill -0 $$(cat $(RUN_DIR)/bank-api.pid) 2>/dev/null; then echo "bank-api already running (pid $$(cat $(RUN_DIR)/bank-api.pid))"; else \
	  nohup uv run bank_api/server.py > $(RUN_DIR)/bank-api.log 2>&1 & echo $$! > $(RUN_DIR)/bank-api.pid; echo "bank-api  starting on http://127.0.0.1:$(VGB_PORT)  (pid $$(cat $(RUN_DIR)/bank-api.pid))"; fi
	@for i in $$(seq 1 40); do curl -sf -o /dev/null http://127.0.0.1:$(VGB_PORT)/ && break; sleep 0.25; done
	@if [ -f $(RUN_DIR)/mcp.pid ] && kill -0 $$(cat $(RUN_DIR)/mcp.pid) 2>/dev/null; then echo "mcp       already running (pid $$(cat $(RUN_DIR)/mcp.pid))"; else \
	  VGB_API_URL=http://127.0.0.1:$(VGB_PORT) nohup uv run python -m kyc_workflow.mcp_server --transport http --port $(MCP_PORT) > $(RUN_DIR)/mcp.log 2>&1 & echo $$! > $(RUN_DIR)/mcp.pid; echo "mcp       starting on http://127.0.0.1:$(MCP_PORT)/mcp  (pid $$(cat $(RUN_DIR)/mcp.pid))"; fi
	@uv run python -m kyc_workflow.mcp_server --check --port $(MCP_PORT) > /dev/null
	@if [ -f $(RUN_DIR)/ui.pid ] && kill -0 $$(cat $(RUN_DIR)/ui.pid) 2>/dev/null; then echo "ui        already running (pid $$(cat $(RUN_DIR)/ui.pid))"; else \
	  MCP_URL=http://127.0.0.1:$(MCP_PORT)/mcp nohup uv run python -m kyc_workflow.ui --port $(UI_PORT) > $(RUN_DIR)/ui.log 2>&1 & echo $$! > $(RUN_DIR)/ui.pid; echo "ui        starting on http://127.0.0.1:$(UI_PORT)  (pid $$(cat $(RUN_DIR)/ui.pid))"; fi
	@$(MAKE) --no-print-directory status

restart: ## Stop and start everything (use after changing server code)
	@$(MAKE) --no-print-directory down
	@$(MAKE) --no-print-directory up

down: ## Stop what `make up` started
	@for svc in ui mcp bank-api; do \
	  if [ -f $(RUN_DIR)/$$svc.pid ]; then pid=$$(cat $(RUN_DIR)/$$svc.pid); pkill -TERM -P $$pid 2>/dev/null; kill -TERM $$pid 2>/dev/null; rm -f $(RUN_DIR)/$$svc.pid; echo "$$svc stopped"; else echo "$$svc not running"; fi; done

status: ## Check both services answer: bank API index, MCP tool list
	@curl -sf "http://127.0.0.1:$(VGB_PORT)/" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("bank-api  up   ", len(d["datasets"]), "datasets from", d["data_dir"])' || echo "bank-api  DOWN  (http://127.0.0.1:$(VGB_PORT))"
	@uv run python -m kyc_workflow.mcp_server --check --port $(MCP_PORT) || echo "mcp       DOWN  (http://127.0.0.1:$(MCP_PORT)/mcp)"
	@for i in $$(seq 1 40); do curl -sf -o /dev/null http://127.0.0.1:$(UI_PORT)/api/status && break; sleep 0.25; done; \
	  curl -sf http://127.0.0.1:$(UI_PORT)/api/status | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ui        up    http://127.0.0.1:$(UI_PORT)  model", d["model"], "|", len(d["tools"]), "tools")' || echo "ui        DOWN  (http://127.0.0.1:$(UI_PORT))"

bank-api: ## Run the bank's reference data API (HTTP) over ./data (Ctrl+C stops it)
	uv run bank_api/server.py

bank-api-check: ## Hit a running bank API: index, then one keyed call
	@curl -sf "http://127.0.0.1:$(VGB_PORT)/" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("data_dir:", d["data_dir"]); print("datasets:", ", ".join(d["datasets"]))'
	@curl -sf -H "X-VGB-API-Key: $(VGB_API_KEY)" "http://127.0.0.1:$(VGB_PORT)/api/customers?limit=1" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("keyed call ok, first customer:", d["rows"][0]["customer_ref"])'

mcp: ## Run the MCP server over stdio in the foreground (needs the bank API; VGB_API_URL to point elsewhere)
	uv run python -m kyc_workflow.mcp_server

ui: ## Run the web UI in the foreground (needs bank API and MCP server; UI_PORT to change port)
	uv run python -m kyc_workflow.ui --port $(UI_PORT)

mcp-tools: ## List the MCP server's tools and their one-line descriptions
	uv run python -m kyc_workflow.mcp_server --list

test: ## Run the offline pytest suite (no network, no key)
	uv run pytest -m "not integration"

test-live: ## Run the live tests: one call through Helios with KYC_EVAL_MODEL (needs ANTHROPIC_API_KEY in .env)
	uv run pytest -m integration

ping: ## One structured call through the gateway with the configured model (MODEL=... to override)
	uv run main.py ping $(if $(MODEL),--model $(MODEL),)

chat: up ## Chat over the records through the running MCP server with guardrails (make up first; MODEL=..., MCP=URL|stdio)
	uv run main.py chat $(if $(MODEL),--model $(MODEL),) $(if $(MCP),--mcp $(MCP),) $(if $(VERBOSE),-v,)

pack: ## Build the evidence pack for a review: make pack REVIEW=VGB-PR-2026-1173 (make up first; NO_MODEL=1 for code only)
	uv run main.py pack $(REVIEW) $(if $(MODEL),--model $(MODEL),) $(if $(NO_MODEL),--no-model,) -v

eval-routing: ## Routing eval against the running MCP server's tools, Ragas-scored (make up first, needs .env; MODEL=...)
	uv run python -m evals.routing.run $(if $(MODEL),--model $(MODEL),)

eval-pack: ## Evidence pack eval over the QA sample (make up first; LIMIT=8 ONLY=overturned MODEL=... NO_RAGAS=1)
	uv run python -m evals.pack.run $(if $(LIMIT),--limit $(LIMIT),) $(if $(ONLY),--only $(ONLY),) $(if $(MODEL),--model $(MODEL),) $(if $(NO_RAGAS),--no-ragas,)

eval-guardrails: ## Guardrail eval: injection, off-topic, impersonation, fabrication through the real chat, Ragas-judged (make up first; MODEL=..., JUDGE=...)
	uv run python -m evals.guardrails.run $(if $(MODEL),--model $(MODEL),) $(if $(JUDGE),--judge-model $(JUDGE),)
