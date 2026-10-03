import pytest

from news_insight.config import Settings


def test_defaults_follow_requirements() -> None:
    settings = Settings(_env_file=None)

    assert settings.timezone == "Asia/Seoul"
    assert settings.lm_studio_model == "qwen/qwen3.8-27b"
    assert settings.admin_email == "ddangggoma@gmail.com"
    assert settings.fetch_timeout_seconds == 15.0
    assert settings.fetch_max_redirects == 3
    assert settings.fetch_max_bytes == 5 * 1024 * 1024


def test_local_defaults_use_reserved_dev_ports() -> None:
    settings = Settings(_env_file=None)

    assert "@localhost:8720/" in settings.database_url
    assert settings.redis_url == "redis://localhost:8721/0"


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    assert Settings(_env_file=None).database_url == "postgresql+psycopg://u:p@db:5432/x"


def test_collection_defaults() -> None:
    assert Settings(_env_file=None).domain_rate_per_minute == 30
