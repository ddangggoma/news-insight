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
compose_check() { docker compose --env-file .env.example config --quiet; }
alembic_check() { (cd "$API" && uv run alembic check); }

verify() {
  local step
  for step in db migrate api_lint api_test alembic_check web_test web_check compose_check; do
    printf '\n==> %s\n' "${step//_/-}"
    "$step"
  done
  printf '\nverify: all checks passed\n'
}

COMMANDS="up down logs db migrate api-dev web-dev api-test api-lint web-test web-check compose-check alembic-check verify"

usage() {
  echo "usage: scripts/dev.sh <command>"
  echo "commands: $COMMANDS"
}

if [[ $# -ne 1 ]] || [[ " $COMMANDS " != *" $1 "* ]]; then
  usage
  exit 2
fi
"${1//-/_}"
