#!/usr/bin/env bash
# Register Korean card generation with launchd every 10 minutes (macOS host, where agy is logged in).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGY="$(command -v agy)"
TARGET="$HOME/Library/LaunchAgents/com.newsinsight.cards.plist"
mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" -e "s#__PATH__#$(dirname "$AGY"):$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin#g" \
    -e "s#__AGY__#$AGY#g" "$ROOT/ops/launchd/com.newsinsight.cards.plist.template" > "$TARGET"
launchctl bootout "gui/$(id -u)/com.newsinsight.cards" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "installed: $TARGET (runs every 10 minutes)"
