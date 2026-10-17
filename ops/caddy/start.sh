#!/bin/sh
# Caddy's ports are published on the Mac's loopback only (compose.yaml), and Docker Desktop relays
# those connections from this network's gateway. The edge proxy on the Mac (ops/edge/proxy.py) is
# what connects there: it starts each connection with a PROXY header carrying the visitor's
# address. Trust that header from the gateway alone (ops/Caddyfile, servers > proxy_protocol).
# The gateway is read at each start, so a recreated network with a new subnet still works.
set -eu
if [ -z "${CADDY_PROXY_FROM:-}" ]; then
	gateway="$(ip -4 route show default | awk '{ print $3; exit }')"
	if [ -n "$gateway" ]; then
		export CADDY_PROXY_FROM="$gateway/32"
	fi
fi
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
