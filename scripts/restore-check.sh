#!/usr/bin/env bash
# Restore rehearsal (P9): decrypt the newest backup into a scratch database
# (news_insight_restore), compare row counts with the live database, then drop it.
# The live database is only read. Usage: scripts/restore-check.sh [backup.dump.age]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/NewsInsightBackups}"
BACKUP_KEY="${BACKUP_KEY:-$HOME/.config/news-insight/backup.age.key}"
SCRATCH=news_insight_restore
env_value() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\"" || true; }
DB_USER="$(env_value POSTGRES_USER)"; DB_USER="${DB_USER:-news}"
LIVE="$(env_value POSTGRES_DB)"; LIVE="${LIVE:-news_insight}"
FILE="${1:-$(ls -t "$BACKUP_DIR"/"$LIVE"-*.dump.age 2>/dev/null | head -1)}"
[[ -n "$FILE" && -f "$FILE" ]] || { echo "no backup found in $BACKUP_DIR" >&2; exit 1; }
psql() { docker compose -f "$ROOT/compose.yaml" exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "$DB_USER" "$@"; }

echo "rehearsing restore of $(basename "$FILE")"
if grep -q "$(basename "$FILE")" "$BACKUP_DIR/SHA256SUMS" 2>/dev/null; then
  (cd "$(dirname "$FILE")" && grep "$(basename "$FILE")" SHA256SUMS | shasum -a 256 -c - >/dev/null) \
    && echo "checksum ok" || { echo "checksum mismatch" >&2; exit 1; }
fi
psql -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH" -c "CREATE DATABASE $SCRATCH"
trap 'psql -d postgres -c "DROP DATABASE IF EXISTS '"$SCRATCH"'" >/dev/null' EXIT
started=$(date +%s)
age -d -i "$BACKUP_KEY" "$FILE" \
  | docker compose -f "$ROOT/compose.yaml" exec -T postgres pg_restore -U "$DB_USER" -d "$SCRATCH" --no-owner --exit-on-error
echo "restored in $(( $(date +%s) - started ))s"

status=0
printf '%-22s %12s %12s\n' table restored live
for table in alembic_version sources items item_cards stories briefings digests strategy_runs; do
  restored=$(psql -d "$SCRATCH" -tA -c "SELECT count(*) FROM $table")
  live=$(psql -d "$LIVE" -tA -c "SELECT count(*) FROM $table")
  printf '%-22s %12s %12s\n' "$table" "$restored" "$live"
  # the backup is older than the live database: it may have fewer rows, never more
  if (( restored > live )) || { (( live > 0 )) && (( restored == 0 )) && [[ $table != briefings ]]; }; then status=1; fi
done
revision_backup=$(psql -d "$SCRATCH" -tA -c "SELECT version_num FROM alembic_version")
revision_live=$(psql -d "$LIVE" -tA -c "SELECT version_num FROM alembic_version")
echo "schema revision: backup $revision_backup, live $revision_live"
(( status == 0 )) && echo "restore rehearsal: OK" || { echo "restore rehearsal: FAILED" >&2; exit 1; }
