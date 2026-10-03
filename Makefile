.PHONY: up down logs db migrate api-dev web-dev api-test api-lint web-test web-check compose-check alembic-check verify

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

db:
	docker compose up -d --wait postgres redis

migrate:
	cd apps/api && uv run alembic upgrade head

api-dev:
	cd apps/api && uv run uvicorn news_insight.main:app --reload --host 127.0.0.1 --port 8711

web-dev:
	cd apps/web && npm run dev

api-test:
	cd apps/api && uv run pytest

api-lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy

web-test:
	cd apps/web && npm test -- --run

web-check:
	cd apps/web && npm run typecheck && npm run build

compose-check:
	docker compose --env-file .env.example config --quiet

alembic-check:
	cd apps/api && uv run alembic check

verify: db migrate api-lint api-test alembic-check web-test web-check compose-check
