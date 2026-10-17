# Caddy with the rate_limit handler (checklist OPS-2). Pinned module version.
FROM caddy:2.10-builder-alpine AS builder
RUN xcaddy build --with github.com/mholt/caddy-ratelimit@v0.1.0

FROM caddy:2.10-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# resolves CADDY_PROXY_FROM=gateway to this container's gateway (host proxy, 2026-10-17)
COPY start.sh /usr/local/bin/caddy-start
ENTRYPOINT ["/usr/local/bin/caddy-start"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
