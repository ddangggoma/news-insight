#!/usr/bin/env bash
# Rollback (P9): switch the app containers back to an earlier image tag without migrating.
# Migrations are additive, so older code runs on the newer schema; if a release changed data
# in an incompatible way, restore the pre-release backup instead (scripts/restore.sh).
# Usage: scripts/rollback.sh [tag]   (default: the tag before the current one in ops/releases.log)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TAG="${1:-$(tail -1 ops/releases.log 2>/dev/null | cut -f3)}"
[[ -n "$TAG" ]] || { echo "no previous release recorded; pass a tag" >&2; exit 1; }
for image in news-insight-api news-insight-web; do
  docker image inspect "$image:$TAG" >/dev/null 2>&1 || { echo "missing image $image:$TAG" >&2; exit 1; }
done
python3 - "$TAG" <<'PY'
import pathlib, sys
path = pathlib.Path(".env")
lines = [l for l in path.read_text().splitlines() if not l.startswith("IMAGE_TAG=")]
path.write_text("\n".join(lines + [f"IMAGE_TAG={sys.argv[1]}"]) + "\n")
PY
# --no-deps skips the migrate service: older code must not try to migrate a newer schema
docker compose up -d --no-build --no-deps api worker scheduler web
printf '%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TAG" "rollback" >> ops/releases.log
echo "rolled back to $TAG"
