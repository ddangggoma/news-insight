#!/usr/bin/env bash
# Register the trend report queue with launchd (macOS host, where the Claude CLI is logged in):
# every minute, `news-insight reports run` writes what readers asked for on /reports (plan 17 R1).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE="$(command -v claude)"
TARGET="$HOME/Library/LaunchAgents/com.newsinsight.reports.plist"
mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" -e "s#__PATH__#$(dirname "$CLAUDE"):$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin#g" \
    -e "s#__CLAUDE__#$CLAUDE#g" "$ROOT/ops/launchd/com.newsinsight.reports.plist.template" > "$TARGET"
launchctl bootout "gui/$(id -u)/com.newsinsight.reports" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "installed: $TARGET (checks the report queue every minute)"
