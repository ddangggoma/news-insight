#!/usr/bin/env bash
# Register the host watchdog (ops/watchdog/watchdog.py) with launchd on this Mac: every 5 minutes
# and at login it checks Docker, the containers, the site, collection, cards, the Claude login and
# today's briefing from outside Docker, starts Docker Desktop when it is down, and pushes alerts
# (docs/runbooks/operations.md §14). deploy.sh runs this when the job is missing or changed.
#
#   scripts/install-watchdog.sh               # install or restart, from NEWS_INSIGHT-live
#   scripts/install-watchdog.sh --uninstall   # stop it and remove the job
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL=com.newsinsight.watchdog
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [[ "${1:-}" == --uninstall ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$TARGET"
  echo "removed: $TARGET"
  exit 0
fi
# the job watches the stack this tree deploys: a dev-tree checkout must not take it over
[[ "$ROOT" == */NEWS_INSIGHT-live || -n "${FORCE:-}" ]] || {
  echo "install from the live worktree (NEWS_INSIGHT-live), or FORCE=1" >&2
  exit 1
}
DOCKER_DIR="$(dirname "$(command -v docker 2>/dev/null || echo /usr/local/bin/docker)")"
mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" -e "s#__PATH__#$DOCKER_DIR:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin#g" \
    "$ROOT/ops/launchd/$LABEL.plist.template" > "$TARGET"
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$TARGET"
echo "installed: $TARGET (every 5 minutes and at login, log ops/logs/watchdog.log)"
echo "channels: $(/usr/bin/python3 "$ROOT/ops/watchdog/watchdog.py" --root "$ROOT" --dry-run | tail -1)"
