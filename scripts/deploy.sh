#!/usr/bin/env bash
# Deploy origin/main to the live worktree (NEWS_INSIGHT-live).
#
# `docker compose up -d --build` hung four times on 2026-10-05 (Docker Desktop 24 / Compose
# 2.18): compose renamed the old containers, created new ones and never started them, leaving
# the API down until someone noticed. This script builds first, then replaces only the app
# containers itself and starts them with --no-build. Postgres and Redis are never touched.
#
#   scripts/deploy.sh            # from NEWS_INSIGHT-live
#   WITH_CADDY=1 scripts/deploy.sh   # also replace Caddy (after Caddyfile or image changes)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "$ROOT" == */NEWS_INSIGHT-live || -n "${FORCE:-}" ]] || {
  echo "deploy from the live worktree (NEWS_INSIGHT-live), or FORCE=1" >&2
  exit 1
}
APP=(migrate api worker scheduler web)
[[ -n "${WITH_CADDY:-}" ]] && APP+=(caddy)
log() { printf '%s deploy: %s\n' "$(date +%H:%M:%S)" "$*"; }
healthy() { [[ "$(docker inspect -f '{{.State.Health.Status}}' "news-insight-$1-1" 2>/dev/null)" == healthy ]]; }

PREVIOUS="$(git rev-parse --short=12 HEAD)"
git fetch -q origin
git checkout -q --detach origin/main
TAG="$(git rev-parse --short=12 HEAD)"
log "$PREVIOUS -> $TAG"

# a schema change gets a fresh backup first (the daily one may be a day old)
if [[ "$PREVIOUS" != "$TAG" ]] && ! git diff --quiet "$PREVIOUS" "$TAG" -- apps/api/migrations/versions; then
  log "new migration: backing up first"
  scripts/backup.sh
fi

log "building images (the running stack keeps serving)"
timeout 900 docker compose build

log "replacing ${APP[*]}"
for service in "${APP[@]}"; do
  timeout 90 docker rm -f "news-insight-$service-1" >/dev/null 2>&1 || true
done
timeout 300 docker compose up -d --no-build --no-deps "${APP[@]}" >/dev/null

for service in api web; do
  for _ in $(seq 1 60); do healthy "$service" && break; sleep 3; done
  healthy "$service" || { log "$service is not healthy: docker compose logs $service"; exit 1; }
done
[[ "$(docker inspect -f '{{.State.ExitCode}}' news-insight-migrate-1)" == 0 ]] || {
  log "migration failed: docker compose logs migrate"
  exit 1
}

# drop the web server's cached reader responses so new pages never render old JSON (PERF-3)
docker compose exec -T web node -e "fetch('http://127.0.0.1:3000/internal/revalidate',{method:'POST',headers:{'x-console-key':process.env.CONSOLE_API_KEY}}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
  || log "warning: reader cache revalidation failed"

for path in /radar/week/"$(date +%G-W%V)" /briefings; do
  code="$(curl -sk -o /dev/null -w '%{http_code}' "https://localhost:${CADDY_HTTPS_PORT:-8700}$path")"
  log "smoke $path -> $code"
  [[ "$code" == 200 ]] || exit 1
done
mkdir -p ops
printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TAG" "$PREVIOUS" >> ops/releases.log
log "live: $TAG"
