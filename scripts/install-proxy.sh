#!/usr/bin/env bash
# Put the host proxy (ops/haproxy) in front of Caddy on the live Mac, under launchd, so Caddy
# sees each visitor's address instead of Docker Desktop's gateway (2026-10-17).
#
#   brew install haproxy
#   scripts/install-proxy.sh            # from NEWS_INSIGHT-live, before the deploy that
#                                       # moves Caddy to loopback: the proxy waits for the ports
#   scripts/install-proxy.sh --remove   # back to Docker on the public ports (runbook)
#
# Ports come from .env: CADDY_HTTPS_PORT / CADDY_HTTP_PORT are the public ports the proxy takes,
# CADDY_PUBLISH_HTTPS / CADDY_PUBLISH_HTTP the loopback ports compose gives Caddy.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL=com.newsinsight.proxy
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
if [[ "${1:-}" == --remove ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$TARGET"
  echo "removed $LABEL: take CADDY_PUBLISH_* and CADDY_PROXY_FROM out of .env, then WITH_CADDY=1 scripts/deploy.sh"
  exit 0
fi
HAPROXY=/opt/homebrew/opt/haproxy/bin/haproxy # the opt link survives brew upgrades
[[ -x "$HAPROXY" ]] || { echo "brew install haproxy first" >&2; exit 1; }
[[ -f "$ROOT/.env" ]] || { echo "no .env in $ROOT: run this from NEWS_INSIGHT-live" >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" "$ROOT/.env" | tr -d "\"'" | tail -1; }
HTTPS_PORT="$(env_value CADDY_HTTPS_PORT)" HTTP_PORT="$(env_value CADDY_HTTP_PORT)"
PUBLISH_HTTPS="$(env_value CADDY_PUBLISH_HTTPS)" PUBLISH_HTTP="$(env_value CADDY_PUBLISH_HTTP)"
HTTPS_PORT="${HTTPS_PORT:-8700}" HTTP_PORT="${HTTP_PORT:-8701}"
# Caddy trusts a PROXY header from its loopback ports: they must not be reachable from outside
[[ "$PUBLISH_HTTPS" == 127.0.0.1:* && "$PUBLISH_HTTP" == 127.0.0.1:* ]] || {
  echo "set CADDY_PUBLISH_HTTPS=127.0.0.1:8702 and CADDY_PUBLISH_HTTP=127.0.0.1:8703 in .env first" >&2
  exit 1
}
[[ -n "$(env_value CADDY_PROXY_FROM)" ]] || {
  echo "set CADDY_PROXY_FROM=gateway in .env first (Caddy ignores the header otherwise)" >&2
  exit 1
}
CADDY_HTTPS_PORT="$HTTPS_PORT" CADDY_HTTP_PORT="$HTTP_PORT" CADDY_PUBLISH_HTTPS="$PUBLISH_HTTPS" \
  CADDY_PUBLISH_HTTP="$PUBLISH_HTTP" "$HAPROXY" -c -q -f "$ROOT/ops/haproxy/haproxy.cfg"
mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" -e "s#__HAPROXY__#$HAPROXY#g" -e "s#__HTTPS_PORT__#$HTTPS_PORT#g" \
    -e "s#__HTTP_PORT__#$HTTP_PORT#g" -e "s#__PUBLISH_HTTPS__#$PUBLISH_HTTPS#g" \
    -e "s#__PUBLISH_HTTP__#$PUBLISH_HTTP#g" "$ROOT/ops/launchd/$LABEL.plist.template" > "$TARGET"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "installed: $TARGET (:$HTTPS_PORT -> $PUBLISH_HTTPS, :$HTTP_PORT -> $PUBLISH_HTTP; log ops/logs/proxy.log)"
