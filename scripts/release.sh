#!/usr/bin/env bash
# Release (P9): back up, build images tagged with the commit, migrate and switch over.
# Run on a clean, pushed main. The tag is recorded in .env (IMAGE_TAG) and ops/releases.log.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "$(git branch --show-current)" == "main" ]] || { echo "release from main" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "working tree is not clean" >&2; exit 1; }
TAG="$(git rev-parse --short=12 HEAD)"
PREVIOUS="$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2- || true)"

scripts/backup.sh
IMAGE_TAG="$TAG" docker compose build
python3 - "$TAG" <<'PY'
import pathlib, sys
path = pathlib.Path(".env")
lines = [l for l in path.read_text().splitlines() if not l.startswith("IMAGE_TAG=")]
path.write_text("\n".join(lines + [f"IMAGE_TAG={sys.argv[1]}"]) + "\n")
PY
docker compose up -d --wait
# drop the web server's cached reader responses so new pages never render old JSON (PERF-3)
docker compose exec -T web node -e "fetch('http://127.0.0.1:3000/internal/revalidate',{method:'POST',headers:{'x-console-key':process.env.CONSOLE_API_KEY}}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
  && echo "reader cache revalidated" || echo "warning: reader cache revalidation failed" >&2
mkdir -p ops
printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TAG" "${PREVIOUS:-local}" >> ops/releases.log
curl -skf -o /dev/null "https://localhost:${CADDY_HTTPS_PORT:-8700}/" && echo "release $TAG is live (previous ${PREVIOUS:-local})"
