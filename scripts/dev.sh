#!/usr/bin/env bash
# Development task runner (replaces make, which needs an Xcode license on macOS).
# Usage: scripts/dev.sh <command>   — run without arguments to list commands.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
WEB="$ROOT/apps/web"
cd "$ROOT"

# One compose project serves both worktrees, but bind mounts resolve per worktree: `compose up`
# from the other tree recreates the running containers (2026-10-05: it killed the live database).
owner()         { docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' news-insight-postgres-1 2>/dev/null || true; }
guard()         {
  local o; o="$(owner)"
  if [[ -n "$o" && "$o" != "$ROOT" && -z "${FORCE:-}" ]]; then
    echo "refusing: the stack runs from $o; run this there (or FORCE=1 to take it over)" >&2
    exit 1
  fi
}
healthy()       { [[ "$(docker inspect -f '{{.State.Health.Status}}' "news-insight-$1-1" 2>/dev/null)" == healthy ]]; }
up()            { guard; docker compose up -d --build; }
down()          { guard; docker compose down; }
logs()          { docker compose logs -f --tail=200; }
db()            { if healthy postgres && healthy redis; then return; fi; guard; docker compose up -d --wait postgres redis; }
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
# Signal regression (QA-1): demo corpus at a pinned time → radar JSON → planted patterns (pytest)
QA_DB_URL="postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight_qa_demo"
QA_NOW="2026-10-04T15:00:00+00:00"
radar_qa() {
  local out="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/radar-qa"
  db
  docker compose exec -T postgres psql -q -U news -d postgres -c "DROP DATABASE IF EXISTS news_insight_qa_demo" -c "CREATE DATABASE news_insight_qa_demo" >/dev/null
  (cd "$API" && export DATABASE_URL="$QA_DB_URL" RADAR_DEMO_NOW="$QA_NOW" \
    && uv run alembic upgrade head >/dev/null && uv run news-insight technologies seed >/dev/null \
    && uv run python scripts/radar_demo_seed.py && uv run python scripts/radar_qa_export.py "$out")
  (cd "$API" && RADAR_QA_DIR="$out" uv run pytest -q tests/radar_qa)
}
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
cards()         {
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight cards run)
  # CLU-1: merge stories told in other words or languages (bge-m3 + judge); never fails the card run
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight stories semantic) \
    || echo "stories semantic skipped (LM Studio or Antigravity unavailable)" >&2
}
sources_seed()  { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight sources seed); }

verify() {
  local step
  for step in db api_lint api_test alembic_check web_test web_check compose_check; do
    printf '\n==> %s\n' "${step//_/-}"
    "$step"
  done
  printf '\nverify: all checks passed\n'
}

COMMANDS="up down logs db migrate api-dev web-dev api-test api-lint web-test web-check compose-check alembic-check verify web-e2e radar-qa admin-link digest cards sources-seed"

usage() {
  echo "usage: scripts/dev.sh <command>"
  echo "commands: $COMMANDS"
}

if [[ $# -ne 1 ]] || [[ " $COMMANDS " != *" $1 "* ]]; then
  usage
  exit 2
fi
"${1//-/_}"
