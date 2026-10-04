#!/usr/bin/env bash
# Register the encrypted daily backup (03:00 KST) with launchd on this Mac.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$HOME/Library/LaunchAgents/com.newsinsight.backup.plist"
mkdir -p "$ROOT/ops/logs" "$(dirname "$TARGET")"
sed -e "s#__REPO__#$ROOT#g" "$ROOT/ops/launchd/com.newsinsight.backup.plist.template" > "$TARGET"
launchctl bootout "gui/$(id -u)/com.newsinsight.backup" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "installed: $TARGET (daily 03:00, logs in ops/logs/backup.log)"
