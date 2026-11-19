#!/usr/bin/env bash
# Threads API token helper (docs/runbooks/threads-api.md).
#
#   scripts/threads-token.sh authorize          print the consent URL to open in a browser
#   scripts/threads-token.sh exchange <code>    code -> short-lived -> 60-day token, saved in .env
#   scripts/threads-token.sh refresh            extend the saved token another 60 days
#   scripts/threads-token.sh check              show whose token it is and when it expires
#
# The app id comes from THREADS_APP_ID (or a prompt). The app secret is typed at a hidden
# prompt and never written anywhere. The token goes only into .env as SOURCE_SECRET_THREADS_TOKEN.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
REDIRECT_URI="${THREADS_REDIRECT_URI:-https://localhost/}"
SCOPES="threads_basic,threads_keyword_search,threads_profile_discovery"
GRAPH="https://graph.threads.net"

die() { echo "error: $*" >&2; exit 1; }

app_id() {
  local id="${THREADS_APP_ID:-}"
  if [[ -z "$id" ]]; then read -r -p "Threads app ID: " id; fi
  [[ "$id" =~ ^[0-9]+$ ]] || die "the app ID is a number (Meta app dashboard → App settings → Basic → Threads app ID)"
  echo "$id"
}

app_secret() {
  local secret
  read -r -s -p "Threads app secret (hidden): " secret; echo >&2
  [[ -n "$secret" ]] || die "no app secret"
  echo "$secret"
}

json_field() {  # json_field <name> < json
  python3 -c 'import json,sys; d=json.load(sys.stdin); v=d.get(sys.argv[1]);
if v is None: sys.exit("response: " + json.dumps(d)[:300])
print(v)' "$1"
}

saved_token() {
  [[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found"
  local token
  token="$(grep -E '^SOURCE_SECRET_THREADS_TOKEN=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
  [[ -n "$token" ]] || die "SOURCE_SECRET_THREADS_TOKEN is empty in $ENV_FILE (run exchange first)"
  echo "$token"
}

save_token() {  # save_token <token> <seconds>
  local token="$1" seconds="$2" tmp
  [[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found"
  tmp="$(mktemp)"
  grep -vE '^SOURCE_SECRET_THREADS_TOKEN=' "$ENV_FILE" > "$tmp" || true
  echo "SOURCE_SECRET_THREADS_TOKEN=$token" >> "$tmp"
  cat "$tmp" > "$ENV_FILE" && rm -f "$tmp"
  local days=$(( seconds / 86400 ))
  echo "saved SOURCE_SECRET_THREADS_TOKEN in $ENV_FILE (valid about $days days)."
  echo "restart the worker from NEWS_INSIGHT-live so it reads the new token."
}

case "${1:-}" in
  authorize)
    id="$(app_id)"
    enc_redirect="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$REDIRECT_URI")"
    echo "Open this URL, log in with the Threads tester account and allow access:"
    echo "https://threads.net/oauth/authorize?client_id=$id&redirect_uri=$enc_redirect&scope=$SCOPES&response_type=code"
    echo
    echo "The browser then lands on $REDIRECT_URI?code=... (the page itself fails to load; that is fine)."
    echo "Copy the code value (drop a trailing #_) and run: scripts/threads-token.sh exchange <code>"
    ;;
  exchange)
    code="${2:-}"; code="${code%#_}"
    [[ -n "$code" ]] || die "usage: scripts/threads-token.sh exchange <code>"
    id="$(app_id)"; secret="$(app_secret)"
    short="$(curl -fsS -X POST "$GRAPH/oauth/access_token" \
      --data-urlencode "client_id=$id" --data-urlencode "client_secret=$secret" \
      --data-urlencode "grant_type=authorization_code" --data-urlencode "redirect_uri=$REDIRECT_URI" \
      --data-urlencode "code=$code" | json_field access_token)"
    long="$(curl -fsS -G "$GRAPH/access_token" --data-urlencode "grant_type=th_exchange_token" \
      --data-urlencode "client_secret=$secret" --data-urlencode "access_token=$short")"
    save_token "$(json_field access_token <<<"$long")" "$(json_field expires_in <<<"$long")"
    ;;
  refresh)
    reply="$(curl -fsS -G "$GRAPH/refresh_access_token" --data-urlencode "grant_type=th_refresh_token" \
      --data-urlencode "access_token=$(saved_token)")"
    save_token "$(json_field access_token <<<"$reply")" "$(json_field expires_in <<<"$reply")"
    ;;
  check)
    curl -fsS -G "$GRAPH/v1.0/me" --data-urlencode "fields=id,username" \
      --data-urlencode "access_token=$(saved_token)"; echo
    ;;
  *)
    sed -n '2,10p' "$0"; exit 2
    ;;
esac
