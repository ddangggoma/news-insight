#!/usr/bin/env bash
# Register the 05:00 KST digest with launchd (macOS host, where the Claude CLI is logged in).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE="$(command -v claude)"
TARGET="$HOME/Library/LaunchAgents/com.newsinsight.digest.plist"
mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" -e "s#__PATH__#$(dirname "$CLAUDE"):$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin#g" \
    -e "s#__CLAUDE__#$CLAUDE#g" "$ROOT/ops/launchd/com.newsinsight.digest.plist.template" > "$TARGET"
launchctl bootout "gui/$(id -u)/com.newsinsight.digest" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "installed: $TARGET (runs daily at 05:00 local time)"
