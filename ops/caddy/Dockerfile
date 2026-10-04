# Caddy with the rate_limit handler (checklist OPS-2). Pinned module version.
FROM caddy:2.10-builder-alpine AS builder
RUN xcaddy build --with github.com/mholt/caddy-ratelimit@v0.1.0

FROM caddy:2.10-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
