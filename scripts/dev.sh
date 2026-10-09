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

# First admin account (plan 14), in the running api container. The password is asked for
# twice at a hidden prompt, never put on the command line.
create_admin()  {
  local username name
  read -rp "admin username: " username
  read -rp "display name: " name
  docker compose exec api news-insight users create-admin "$username" --name "$name"
}

# Host job logs (launchd appends to ops/logs/*.log): keep the current file under 20 MB plus 3 old
rotate()        {
  local file="$ROOT/ops/logs/$1.log"
  [[ -f "$file" && $(stat -f%z "$file" 2>/dev/null || stat -c%s "$file") -gt 20971520 ]] || return 0
  rm -f "$file.3"; [[ -f "$file.2" ]] && mv "$file.2" "$file.3"; [[ -f "$file.1" ]] && mv "$file.1" "$file.2"
  mv "$file" "$file.1"
}

# 05:00 KST (launchd): freeze if Celery has not, shortlist, Claude digest, gates, publish
# uv stops reading .env at a line it cannot parse: say so in the job log (keys after it vanish)
env_check()     { "$ROOT/scripts/check-env.sh" || echo "WARNING: .env is not fully readable by uv; keys after the reported line are missing" >&2; }
# then the audio and the weekly/monthly briefing (plan 13 C4): a no-op unless the last week or month has none,
# so Monday's 05:00 run writes the week, and a daily failure never blocks it
digest()        {
  rotate digest; env_check
  local status=0
  (cd "$API" && uv run --env-file "$ROOT/.env" news-insight daily publish) || status=$?
  # spoken briefing with macOS `say` (plan 13 A1), served by Caddy from ops/media
  (cd "$API" && MEDIA_DIR="$ROOT/ops/media" uv run --env-file "$ROOT/.env" news-insight audio render) || true
  # the reader cache may hold the briefing from before its audio existed (10-minute TTL)
  (cd "$ROOT" && docker compose exec -T web node -e "fetch('http://127.0.0.1:3000/internal/revalidate',{method:'POST',headers:{'x-console-key':process.env.CONSOLE_API_KEY}}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))") || true
  (cd "$API" && uv run --env-file "$ROOT/.env" news-insight periodic publish) || true
  return "$status"
}
# Host-side: agy is logged in here, and LM Studio is reached on localhost (not host.docker.internal).
cards()         {
  rotate cards
  env_check
  # macOS memory, swap and the Qwen state for the console (the containers cannot see them)
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight ops host-snapshot) \
    || echo "host snapshot skipped" >&2
  # plan 16 #3: title embeddings and carding priority before the engines pick what to card
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight cards triage) \
    || echo "triage skipped (LM Studio unavailable): cards go newest first" >&2
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight cards run)
  # plan 16 #1: embed new cards (and backfill older ones) for the ask page
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight cards embed) \
    || echo "card embeddings skipped (LM Studio unavailable)" >&2
  # plan 16 #8: deals from the cards, at night only (capped per run)
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight cards deals --night) \
    || echo "deal extraction skipped (LM Studio unavailable)" >&2
  # CLU-1: merge stories told in other words or languages (bge-m3 + judge); never fails the card run
  (cd "$API" && LM_STUDIO_URL=http://127.0.0.1:1234 uv run --env-file "$ROOT/.env" news-insight stories semantic) \
    || echo "stories semantic skipped (LM Studio or Antigravity unavailable)" >&2
}
# Log report and whole-flow audit (host-side, read-only); reports land in ops/reports/
logs_report()   { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight ops logs --root "$ROOT" --write "$ROOT/ops/reports/logs-$(date +%Y%m%d-%H%M).md" >/dev/null) && ls -t "$ROOT"/ops/reports/logs-* | head -1; }
audit()         { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight ops audit --write "$ROOT/ops/reports/audit-$(date +%Y%m%d-%H%M).md" >/dev/null) && ls -t "$ROOT"/ops/reports/audit-* | head -1; }
sources_seed()  { (cd "$API" && uv run --env-file "$ROOT/.env" news-insight sources seed); }

verify() {
  local step
  for step in db api_lint api_test alembic_check web_test web_check compose_check; do
    printf '\n==> %s\n' "${step//_/-}"
    "$step"
  done
  printf '\nverify: all checks passed\n'
}

COMMANDS="up down logs db migrate api-dev web-dev api-test api-lint web-test web-check compose-check alembic-check verify web-e2e radar-qa create-admin digest cards sources-seed logs-report audit"

usage() {
  echo "usage: scripts/dev.sh <command>"
  echo "commands: $COMMANDS"
}

if [[ $# -ne 1 ]] || [[ " $COMMANDS " != *" $1 "* ]]; then
  usage
  exit 2
fi
"${1//-/_}"
