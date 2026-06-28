.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down logs ps rebuild test test-unit fmt seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start the whole stack (api, worker, postgres, redis, minio)
	@test -f .env || cp .env.example .env
	$(COMPOSE) up --build

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Tail logs
	$(COMPOSE) logs -f

ps: ## Show running services
	$(COMPOSE) ps

rebuild: ## Rebuild images from scratch
	$(COMPOSE) build --no-cache

test: ## Run the full test suite inside a container (unit + integration + e2e)
	$(COMPOSE) run --rm api pytest

test-unit: ## Run only the offline unit tests (no services needed)
	$(COMPOSE) run --rm api pytest -m unit

seed: ## POST a sample transcript to a running API
	./scripts/seed.sh

clean: ## Stop and remove volumes
	$(COMPOSE) down -v
