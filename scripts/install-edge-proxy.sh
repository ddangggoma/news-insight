#!/usr/bin/env bash
# Register the edge proxy (ops/edge/proxy.py) with launchd on this Mac. It owns the site's public
# ports and relays to Caddy's loopback ports with each visitor's address in a PROXY header
# (docs/runbooks/operations.md §13). deploy.sh runs this when the job is missing or changed.
#
#   scripts/install-edge-proxy.sh               # install or restart, from NEWS_INSIGHT-live
#   scripts/install-edge-proxy.sh --uninstall   # stop it and remove the job
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL=com.newsinsight.edge
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

stop() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  # bootstrap fails while the old process is still exiting
  for _ in $(seq 1 20); do launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 || return 0; sleep 0.5; done
}

if [[ "${1:-}" == --uninstall ]]; then
  stop
  rm -f "$TARGET"
  echo "removed: $TARGET (nothing listens on the public ports until Caddy publishes them again)"
  exit 0
fi
# the job runs the proxy from this tree: a dev-tree checkout must not change production
[[ "$ROOT" == */NEWS_INSIGHT-live || -n "${FORCE:-}" ]] || {
  echo "install from the live worktree (NEWS_INSIGHT-live), or FORCE=1" >&2
  exit 1
}
env_value() {
  local value
  value="$(sed -n "s/^$1=//p" "$ROOT/.env" 2>/dev/null | tr -d "\"'" | tail -1)"
  echo "${value:-$2}"
}
HTTPS_PORT="$(env_value CADDY_HTTPS_PORT 8700)"
HTTP_PORT="$(env_value CADDY_HTTP_PORT 8701)"
LOCAL_HTTPS_PORT="$(env_value CADDY_LOCAL_HTTPS_PORT 8702)"
LOCAL_HTTP_PORT="$(env_value CADDY_LOCAL_HTTP_PORT 8703)"

mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" -e "s#__HTTPS_PORT__#$HTTPS_PORT#g" -e "s#__HTTP_PORT__#$HTTP_PORT#g" \
    -e "s#__LOCAL_HTTPS_PORT__#$LOCAL_HTTPS_PORT#g" -e "s#__LOCAL_HTTP_PORT__#$LOCAL_HTTP_PORT#g" \
    "$ROOT/ops/launchd/$LABEL.plist.template" > "$TARGET"
stop
launchctl bootstrap "$DOMAIN" "$TARGET"
echo "installed: $TARGET (:$HTTPS_PORT -> 127.0.0.1:$LOCAL_HTTPS_PORT, :$HTTP_PORT -> 127.0.0.1:$LOCAL_HTTP_PORT, log ops/logs/edge.log)"
