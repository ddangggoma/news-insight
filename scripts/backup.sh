#!/usr/bin/env bash
# Encrypted PostgreSQL backup (P9): pg_dump (custom format) piped through age.
# Backups live outside the repository; the age identity is created on first run.
#   BACKUP_DIR (default ~/NewsInsightBackups)   BACKUP_KEEP_DAYS (default 14)
#   BACKUP_KEY (default ~/.config/news-insight/backup.age.key) — keep a copy offline.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/NewsInsightBackups}"
BACKUP_KEY="${BACKUP_KEY:-$HOME/.config/news-insight/backup.age.key}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
env_value() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\"" || true; }
DB_USER="$(env_value POSTGRES_USER)"; DB_USER="${DB_USER:-news}"
DB_NAME="${1:-$(env_value POSTGRES_DB)}"; DB_NAME="${DB_NAME:-news_insight}"

command -v age >/dev/null || { echo "age is required (brew install age)" >&2; exit 1; }
umask 077
mkdir -p "$BACKUP_DIR" "$(dirname "$BACKUP_KEY")"
if [[ ! -f "$BACKUP_KEY" ]]; then
  age-keygen -o "$BACKUP_KEY" 2>/dev/null
  echo "created backup key $BACKUP_KEY — copy it somewhere offline; backups cannot be read without it"
fi
RECIPIENT="$(age-keygen -y "$BACKUP_KEY")"
OUT="$BACKUP_DIR/${DB_NAME}-$(date +%Y%m%d-%H%M%S).dump.age"

docker compose -f "$ROOT/compose.yaml" exec -T postgres pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc \
  | age -r "$RECIPIENT" -o "$OUT.partial"
mv "$OUT.partial" "$OUT"
printf '%s  %s\n' "$(shasum -a 256 "$OUT" | cut -d' ' -f1)" "$(basename "$OUT")" >> "$BACKUP_DIR/SHA256SUMS"
find "$BACKUP_DIR" -name "${DB_NAME}-*.dump.age" -mtime +"$KEEP_DAYS" -print -delete | sed 's/^/expired: /'
echo "backup: $OUT ($(du -h "$OUT" | cut -f1))"
