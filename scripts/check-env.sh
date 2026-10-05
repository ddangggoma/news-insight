#!/usr/bin/env bash
# Refuse an .env that `uv run --env-file` cannot read to the end.
#
# 2026-10-05: an unquoted value with spaces (an app password) made uv stop at that line, so
# every key after it — Codex path, GitHub token, OpenAlex contact — silently vanished from
# the host jobs (cards, digest). Docker Compose reads the same file fine, which hid it.
# Prints the line number and key only, never the value.
set -euo pipefail
FILE="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env}"
[[ -f "$FILE" ]] || exit 0
bad=0
n=0
while IFS= read -r line || [[ -n "$line" ]]; do
  n=$((n + 1))
  [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# ]] && continue
  key="${line%%=*}"
  value="${line#*=}"
  if [[ "$value" =~ [[:space:]] && ! "$value" =~ ^\".*\"$ && ! "$value" =~ ^\'.*\'$ ]]; then
    echo ".env line $n: $key has spaces but no quotes (wrap the value in double quotes)" >&2
    bad=1
  fi
done <"$FILE"
exit "$bad"
