# Convenience targets. Without `make`, run the commands on the right directly.
.PHONY: up down build seed live migrate logs test test-py test-web lint fmt lock

up:            ## Start the whole stack
	docker compose up -d --build

down:          ## Stop the stack (keeps data)
	docker compose down

build:
	docker compose build

migrate:       ## Apply migrations only
	docker compose run --rm migrate

seed:          ## Migrations + full synthetic dataset (wipes core/ops/gold)
	docker compose run --rm seed

live:          ## Continuous transactions through cuentas-api (Ctrl+C to stop)
	docker compose run --rm live

logs:
	docker compose logs -f --tail=100

lock:
	uv lock

test: test-py test-web

test-py:       ## Backend tests (needs the compose postgres running)
	uv run pytest libs services simulator

test-web:
	pnpm -r test

lint:
	uv run ruff check .
	uv run mypy libs/chaski_common/src services/cuentas-api/src services/core-api/src services/ia-api/src simulator/src
	pnpm -r lint

fmt:
	uv run ruff format .
	uv run ruff check --fix .
	pnpm -r format
