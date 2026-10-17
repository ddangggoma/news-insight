#!/bin/sh
# CADDY_PROXY_FROM=gateway (live Mac, behind the host proxy): read a PROXY header only from this
# container's default gateway. Docker's loopback-published ports connect from there (172.19.0.1 on
# news-insight_default, 2026-10-17); the other containers on the network connect from their own
# addresses and are not believed. Read at every start, so a recreated network with a new subnet
# still matches. 192.168.65.0/24 stays trusted in case Docker Desktop moves loopback ports onto its
# VM gateway path; Caddy is only on loopback when this is set (deploy.sh checks).
set -eu
if [ "${CADDY_PROXY_FROM:-}" = gateway ]; then
  gw="$(ip route show default | awk '{ print $3; exit }')"
  [ -n "$gw" ] || { echo "start.sh: no default gateway for CADDY_PROXY_FROM=gateway" >&2; exit 1; }
  export CADDY_PROXY_FROM="$gw/32 192.168.65.0/24"
  echo "start.sh: PROXY headers read only from $CADDY_PROXY_FROM" >&2
fi
exec "$@"
