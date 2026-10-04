#!/usr/bin/env bash
# Disaster recovery (P9): replace the live database with a backup. Destructive — asks to
# type RESTORE. Stops the app containers, restores, migrates to head and starts them again.
# Usage: scripts/restore.sh <backup.dump.age>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_KEY="${BACKUP_KEY:-$HOME/.config/news-insight/backup.age.key}"
FILE="${1:?usage: scripts/restore.sh <backup.dump.age>}"
env_value() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\"" || true; }
DB_USER="$(env_value POSTGRES_USER)"; DB_USER="${DB_USER:-news}"
DB_NAME="$(env_value POSTGRES_DB)"; DB_NAME="${DB_NAME:-news_insight}"
compose() { docker compose -f "$ROOT/compose.yaml" "$@"; }

echo "This replaces database '$DB_NAME' with $(basename "$FILE")."
echo "Take a fresh backup first (scripts/backup.sh) if the current data matters."
read -r -p "Type RESTORE to continue: " answer
[[ "$answer" == "RESTORE" ]] || { echo "aborted"; exit 1; }

compose stop caddy web api worker scheduler
compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "$DB_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS $DB_NAME" -c "CREATE DATABASE $DB_NAME"
age -d -i "$BACKUP_KEY" "$FILE" \
  | compose exec -T postgres pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --exit-on-error
compose up -d
echo "restored $(basename "$FILE"); migrations ran in the migrate service"
