.PHONY: help run db-up db-down db-create-test migrate migrate-down migrate-status migrate-new test release openapi

ENV ?= .env.local

help: ## Show this help (ENV=.env.production make ...)
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

run: ## Start development server with --reload
	uv run --env-file $(ENV) uvicorn app.main:app --reload

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

db-up: ## Start local PostgreSQL (docker-compose)
	docker compose --env-file $(ENV) up -d db

db-down: ## Stop local PostgreSQL
	docker compose --env-file $(ENV) down

db-create-test: ## Create vivac_test database in running container (run once for existing containers)
	docker compose --env-file $(ENV) exec db createdb -U $$(grep '^DB_USER' $(ENV) | cut -d= -f2) vivac_test || true

# ---------------------------------------------------------------------------
# Migration (Alembic)
# ---------------------------------------------------------------------------

migrate: ## Apply all pending migrations (alembic upgrade head)
	uv run --env-file $(ENV) alembic upgrade head

migrate-down: ## Rollback one migration step (alembic downgrade -1)
	uv run --env-file $(ENV) alembic downgrade -1

migrate-status: ## Show current migration status (alembic current)
	uv run --env-file $(ENV) alembic current

migrate-new: ## Create a new migration (usage: make migrate-new m="describe changes")
	uv run --env-file $(ENV) alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

test: ## Run tests against vivac_test database
	uv run --env-file .env.test pytest

# ---------------------------------------------------------------------------
# OpenAPI
# ---------------------------------------------------------------------------

openapi: ## Export OpenAPI spec to docs/openapi.json
	uv run --env-file $(ENV) python -m scripts.export_openapi

# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

release: ## Tag and push a release (usage: make release v=v0.1.0)
	@test -n "$(v)" || (echo "Usage: make release v=v0.1.0" && exit 1)
	@test "$$(git branch --show-current)" = "main" || (echo "Error: must be on main branch (current: $$(git branch --show-current))" && exit 1)
	@test -z "$$(git status --porcelain)" || (echo "Error: working tree is dirty" && exit 1)
	git tag $(v)
	git push origin $(v)
