#!/usr/bin/env bash
# Development task runner (replaces make, which needs an Xcode license on macOS).
# Usage: scripts/dev.sh <command>   — run without arguments to list commands.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
WEB="$ROOT/apps/web"
cd "$ROOT"

up()            { docker compose up -d --build; }
down()          { docker compose down; }
logs()          { docker compose logs -f --tail=200; }
db()            { docker compose up -d --wait postgres redis; }
migrate()       { (cd "$API" && uv run alembic upgrade head); }
api_dev()       { (cd "$API" && uv run uvicorn news_insight.main:app --reload --host 127.0.0.1 --port 8711); }
web_dev()       { (cd "$WEB" && npm run dev); }
api_test()      { (cd "$API" && uv run pytest); }
api_lint()      { (cd "$API" && uv run ruff check . && uv run ruff format --check . && uv run mypy); }
web_test()      { (cd "$WEB" && npm test -- --run); }
web_check()     { (cd "$WEB" && npm run typecheck && npm run build); }
# Playwright against a seeded news_insight_e2e database (system Chrome; API 8712, web 8713)
web_e2e()       { db; e2e_db; (cd "$WEB" && npx playwright test); }
e2e_db()        { docker compose exec -T postgres psql -q -U news -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'news_insight_e2e'" | grep -q 1 || docker compose exec -T postgres psql -q -U news -d postgres -c "CREATE DATABASE news_insight_e2e"; }
compose_check() { docker compose --env-file .env.example config --quiet; }
# Migrations are checked on a scratch database: verify must never change the live schema.
CHECK_DB_URL="postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight_check"
alembic_check() {
  docker compose exec -T postgres psql -q -U news -d postgres -c "DROP DATABASE IF EXISTS news_insight_check" -c "CREATE DATABASE news_insight_check" >/dev/null
  (cd "$API" && DATABASE_URL="$CHECK_DB_URL" uv run alembic upgrade head >/dev/null && DATABASE_URL="$CHECK_DB_URL" uv run alembic check)
}

# Admin magic link without SMTP: prints a single-use 15-minute login URL (P8).
admin_link()    { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight admin link); }

# 05:00 KST (launchd): freeze if Celery has not, shortlist, Claude digest, gates, publish
digest()        { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight daily publish); }
# Host-side: agy is logged in here, and LM Studio is reached on localhost (not host.docker.internal).
cards()         { (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight cards run); }
sources_seed()  { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight sources seed); }

verify() {
  local step
  for step in db api_lint api_test alembic_check web_test web_check compose_check; do
    printf '\n==> %s\n' "${step//_/-}"
    "$step"
  done
  printf '\nverify: all checks passed\n'
}

COMMANDS="up down logs db migrate api-dev web-dev api-test api-lint web-test web-check compose-check alembic-check verify web-e2e admin-link digest cards sources-seed"

usage() {
  echo "usage: scripts/dev.sh <command>"
  echo "commands: $COMMANDS"
}

if [[ $# -ne 1 ]] || [[ " $COMMANDS " != *" $1 "* ]]; then
  usage
  exit 2
fi
"${1//-/_}"
