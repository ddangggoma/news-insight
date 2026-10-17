from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_services() -> dict[str, Any]:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services: dict[str, Any] = compose["services"]
    return services


def test_stack_defines_every_runtime_service() -> None:
    expected = {"migrate", "web", "api", "worker", "scheduler", "postgres", "redis", "caddy"}

    assert expected <= set(load_services())


def test_data_store_major_versions_are_pinned() -> None:
    services = load_services()

    # postgres is built from ops/postgres (pgvector on the same Alpine base, plan 15-6)
    dockerfile = (
        Path(__file__).resolve().parents[3]
        / services["postgres"]["build"]["context"]
        / "Dockerfile"
    )
    assert "FROM postgres:16-alpine" in dockerfile.read_text()
    assert services["postgres"]["image"].startswith("news-insight-postgres:16")
    assert services["redis"]["image"].startswith("redis:7")


def test_only_caddy_publishes_host_ports() -> None:
    published = {name for name, service in load_services().items() if service.get("ports")}

    assert published == {"caddy"}


def test_caddy_publishes_only_reserved_dev_ports() -> None:
    ports = load_services()["caddy"]["ports"]

    # unset CADDY_PUBLISH_* (everywhere but the live Mac) keeps 8700/8701 on all addresses
    assert ports == [
        "${CADDY_PUBLISH_HTTPS:-${CADDY_HTTPS_PORT:-8700}}:${CADDY_HTTPS_PORT:-8700}",
        "${CADDY_PUBLISH_HTTP:-${CADDY_HTTP_PORT:-8701}}:${CADDY_HTTP_PORT:-8701}",
    ]


def test_caddy_reads_proxy_headers_only_from_the_configured_gateway() -> None:
    caddyfile = (REPO_ROOT / "ops" / "Caddyfile").read_text(encoding="utf-8")
    proxy = (REPO_ROOT / "ops" / "haproxy" / "haproxy.cfg").read_text(encoding="utf-8")

    # the host proxy (live Mac) names the visitor in a PROXY v2 header; TLS stays with Caddy
    assert load_services()["caddy"]["environment"]["CADDY_PROXY_FROM"] == "${CADDY_PROXY_FROM:-}"
    assert "allow {$CADDY_PROXY_FROM}" in caddyfile
    # unset, nothing is read: a header from anyone else is never trusted
    assert "fallback_policy skip" in caddyfile
    assert caddyfile.index("proxy_protocol {") < caddyfile.index("\t\t\ttls\n")
    assert proxy.count("send-proxy-v2") == 2
    assert "mode tcp" in proxy


def test_dev_override_binds_stores_to_loopback_reserved_ports() -> None:
    override = yaml.safe_load((REPO_ROOT / "compose.override.yaml").read_text(encoding="utf-8"))

    assert override["services"]["postgres"]["ports"] == ["127.0.0.1:8720:5432"]
    assert override["services"]["redis"]["ports"] == ["127.0.0.1:8721:6379"]


def test_worker_can_reach_host_lm_studio() -> None:
    worker = load_services()["worker"]

    assert "host.docker.internal:host-gateway" in worker["extra_hosts"]
    assert worker["environment"]["LM_STUDIO_MODEL"].endswith("qwen/qwen3.8-27b}")


def test_console_key_reaches_api_and_web() -> None:
    services = load_services()

    assert "CONSOLE_API_KEY" in services["api"]["environment"]
    assert "CONSOLE_API_KEY" in services["web"]["environment"]


def test_caddy_hides_the_admin_api() -> None:
    caddyfile = (REPO_ROOT / "ops" / "Caddyfile").read_text(encoding="utf-8")

    # /console itself is guarded by the web server's magic-link session (P8)
    assert "basic_auth" not in caddyfile
    assert "handle @admin_api {" in caddyfile


def test_magic_link_settings_reach_python_services() -> None:
    env = load_services()["api"]["environment"]

    for name in ("PUBLIC_BASE_URL", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"):
        assert name in env


def test_caddy_limits_pages_per_session_and_explains_refusals() -> None:
    caddyfile = (REPO_ROOT / "ops" / "Caddyfile").read_text(encoding="utf-8")

    # without the host proxy every visitor is one gateway IP: a per-IP page budget is site-wide
    assert "key {remote_host}:{http.request.cookie.ni_session}" in caddyfile
    assert "zone site {" in caddyfile
    # refusals and upstream failures get a page that reloads itself, not an empty 429
    assert "handle_errors 429 502 503 504 {" in caddyfile
    assert '<meta http-equiv="refresh"' in caddyfile


def test_api_bounds_its_concurrent_requests() -> None:
    env = load_services()["api"]["environment"]

    assert int(env["API_MAX_INFLIGHT"]) > 0
    assert float(env["API_QUEUE_SECONDS"]) > 0


def test_caddy_lets_only_the_report_view_into_a_same_origin_frame() -> None:
    caddyfile = (REPO_ROOT / "ops" / "Caddyfile").read_text(encoding="utf-8")

    # the site refuses every frame; a trend report (plan 17 R1) opens in /reports/{id}'s frame
    # (2026-10-13: the blanket DENY left that frame "refused to connect")
    assert "@framed_report path_regexp framed_report ^/reports/[0-9]+/view$" in caddyfile
    assert "@site_pages not path_regexp site_pages ^/reports/[0-9]+/view$" in caddyfile
    framed, rest = caddyfile.split("header @framed_report {", 1)[1].split("}", 1)
    assert "X-Frame-Options SAMEORIGIN" in framed and "frame-ancestors 'self'" in framed
    site = rest.split("header @site_pages {", 1)[1].split("}", 1)[0]
    assert "X-Frame-Options DENY" in site and "frame-ancestors 'none'" in site
