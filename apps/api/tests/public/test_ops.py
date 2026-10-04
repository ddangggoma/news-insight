from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_caddy_keeps_the_reader_api_internal() -> None:
    caddyfile = (REPO_ROOT / "ops" / "Caddyfile").read_text(encoding="utf-8")
    assert "@public_api path /api/public /api/public/*" in caddyfile
    assert "handle @public_api {\n\t\trespond 404" in caddyfile


def test_compose_passes_the_public_key_to_api_and_web() -> None:
    compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "PUBLIC_API_KEY" in services["api"]["environment"]
    assert "PUBLIC_API_KEY" in services["web"]["environment"]
