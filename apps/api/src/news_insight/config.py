from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Defaults encode the v1.0 requirement constants."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://news:news-dev-password@localhost:5432/news_insight"
    redis_url: str = "redis://localhost:6379/0"
    timezone: str = "Asia/Seoul"
    lm_studio_url: str = "http://host.docker.internal:1234"
    lm_studio_model: str = "qwen/qwen3.8-27b"
    admin_email: str = "ddangggoma@gmail.com"
    fetch_timeout_seconds: float = 15.0
    fetch_max_redirects: int = 3
    fetch_max_bytes: int = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
