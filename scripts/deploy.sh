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

PREVIOUS="${DEPLOY_PREVIOUS:-$(git rev-parse --short=12 HEAD)}"
if [[ -z "${DEPLOY_PREVIOUS:-}" ]]; then
  git fetch -q origin
  git checkout -q --detach origin/main
  # bash reads a script as it runs: start again so this deploy uses the script it just checked out
  DEPLOY_PREVIOUS="$PREVIOUS" exec "$ROOT/scripts/deploy.sh" "$@"
fi
TAG="$(git rev-parse --short=12 HEAD)"
log "$PREVIOUS -> $TAG"

# host jobs read .env with uv, which stops at the first line it cannot parse
scripts/check-env.sh || { log "fix .env first (values with spaces need quotes)"; exit 1; }

# Behind the host proxy (scripts/install-proxy.sh) Caddy trusts a PROXY header naming the
# visitor: its ports must then be loopback-only, and the proxy must hold the public ones
env_value() { sed -n "s/^$1=//p" .env 2>/dev/null | tr -d "\"'" | tail -1; }
loopback=0
[[ "$(env_value CADDY_PUBLISH_HTTPS)" == 127.0.0.1:* && "$(env_value CADDY_PUBLISH_HTTP)" == 127.0.0.1:* ]] && loopback=1
if [[ -n "$(env_value CADDY_PROXY_FROM)" && "$loopback" == 0 ]]; then
  log "CADDY_PROXY_FROM needs CADDY_PUBLISH_HTTPS and CADDY_PUBLISH_HTTP on 127.0.0.1"
  exit 1
fi
if [[ "$loopback" == 1 ]] && ! launchctl print "gui/$(id -u)/com.newsinsight.proxy" >/dev/null 2>&1; then
  log "Caddy is published on loopback but the host proxy is not loaded: scripts/install-proxy.sh"
  exit 1
fi

# a schema change gets a fresh backup first (the daily one may be a day old)
if [[ "$PREVIOUS" != "$TAG" ]] && ! git diff --quiet "$PREVIOUS" "$TAG" -- apps/api/migrations/versions; then
  log "new migration: backing up first"
  scripts/backup.sh
fi

log "building images (the running stack keeps serving)"
timeout 900 docker compose build

log "replacing ${APP[*]}"
# a removed container takes its log with it: keep it for `news-insight ops logs` (7 days)
ARCHIVE="$ROOT/ops/logs/containers"
mkdir -p "$ARCHIVE"
for service in "${APP[@]}"; do
  timeout 60 docker logs --timestamps "news-insight-$service-1" >"$ARCHIVE/$service-$(date +%Y%m%d-%H%M%S).log" 2>&1 || true
  timeout 90 docker rm -f "news-insight-$service-1" >/dev/null 2>&1 || true
done
find "$ARCHIVE" -name '*.log' -mtime +7 -delete
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

# Caddy only holds a certificate for PUBLIC_HOST (an IP since 2026-10-05): ask for that name,
# connected to the local port, so the check needs neither DNS nor hairpin NAT
HOST="$(env_value PUBLIC_HOST)"
HOST="${HOST:-localhost}"
PORT="${CADDY_HTTPS_PORT:-8700}"
# Every page needs a login since plan 14: the login page answers 200 and a protected page
# redirects to it (a 200 there would mean the session check is gone, a 5xx a broken release)
for check in "/login 200" "/briefings 307" /radar/week/"$(date +%G-W%V)"" 307"; do
  path="${check% *}" want="${check##* }"
  # Caddy rate-limits pages per session and /login per IP: a 429 means wait, not a broken release
  for attempt in 1 2 3 4; do
    reply="$(curl -sk -o /dev/null -w '%{http_code} %{redirect_url}' \
      --connect-to "$HOST:$PORT:127.0.0.1:$PORT" "https://$HOST:$PORT$path" || true)"
    code="${reply%% *}"
    [[ "$code" == 429 && "$attempt" -lt 4 ]] || break
    sleep 20
  done
  log "smoke $path -> $reply"
  [[ "$code" == "$want" ]] || exit 1
  [[ "$want" != 307 || "${reply#* }" == */login* ]] || exit 1
done
mkdir -p ops
printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TAG" "$PREVIOUS" >> ops/releases.log

# every build leaves the previous :local images untagged and adds build cache: after 63
# deploys they filled Docker Desktop's 58 GB disk (2026-10-17) and Postgres failed every
# reader query with DiskFull. Rollback rebuilds from git, so neither is needed.
timeout 300 docker image prune -f >/dev/null || log "warning: image prune failed"
timeout 300 docker builder prune -f --keep-storage "${BUILD_CACHE_KEEP:-8GB}" >/dev/null \
  || log "warning: build cache prune failed"
log "live: $TAG"
