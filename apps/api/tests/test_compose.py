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

    assert services["postgres"]["image"].startswith("postgres:16")
    assert services["redis"]["image"].startswith("redis:7")


def test_only_caddy_publishes_host_ports() -> None:
    published = {name for name, service in load_services().items() if service.get("ports")}

    assert published == {"caddy"}


def test_caddy_publishes_only_reserved_dev_ports() -> None:
    ports = load_services()["caddy"]["ports"]

    assert ports == [
        "${CADDY_HTTPS_PORT:-8700}:${CADDY_HTTPS_PORT:-8700}",
        "${CADDY_HTTP_PORT:-8701}:${CADDY_HTTP_PORT:-8701}",
    ]


def test_dev_override_binds_stores_to_loopback_reserved_ports() -> None:
    override = yaml.safe_load((REPO_ROOT / "compose.override.yaml").read_text(encoding="utf-8"))

    assert override["services"]["postgres"]["ports"] == ["127.0.0.1:8720:5432"]
    assert override["services"]["redis"]["ports"] == ["127.0.0.1:8721:6379"]


def test_worker_can_reach_host_lm_studio() -> None:
    worker = load_services()["worker"]

    assert "host.docker.internal:host-gateway" in worker["extra_hosts"]
    assert worker["environment"]["LM_STUDIO_MODEL"].endswith("qwen/qwen3.8-27b}")
