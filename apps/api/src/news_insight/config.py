from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Defaults encode the v1.0 requirement constants."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight"
    redis_url: str = "redis://localhost:8721/0"
    timezone: str = "Asia/Seoul"
    lm_studio_url: str = "http://host.docker.internal:1234"
    lm_studio_model: str = "qwen/qwen3.8-27b"
    admin_email: str = "ddangggoma@gmail.com"
    fetch_timeout_seconds: float = 15.0
    fetch_max_redirects: int = 3
    fetch_max_bytes: int = 5 * 1024 * 1024
    domain_rate_per_minute: int = 30
    console_api_key: str = ""
    claude_cli: str = "claude"
    digest_model: str = "opus"
    digest_timeout_seconds: int = 900
    agy_cli: str = "agy"
    card_agy_model: str = "gemini-3.8-flash-low"
    card_agy_min_weekly: int = 10
    card_agy_min_five_hour: int = 2
    card_agy_batch: int = 100
    card_agy_parallel: int = 3
    card_qwen_batch: int = 5
    card_timeout_seconds: int = 300
    card_time_budget_seconds: int = 540


@lru_cache
def get_settings() -> Settings:
    return Settings()
