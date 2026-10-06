from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Defaults encode the v1.0 requirement constants."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight"
    redis_url: str = "redis://localhost:8721/0"
    timezone: str = "Asia/Seoul"
    openalex_mailto: str = ""  # contact address for the OpenAlex polite pool (in .env only)
    lm_studio_url: str = "http://host.docker.internal:1234"
    lm_studio_model: str = "qwen/qwen3.8-27b"
    lm_studio_embedding_model: str = "text-embedding-bge-m3"  # multilingual story merging (C1)
    admin_email: str = "ddangggoma@gmail.com"
    public_base_url: str = "https://localhost:8700"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    fetch_timeout_seconds: float = 15.0
    fetch_max_redirects: int = 3
    fetch_max_bytes: int = 5 * 1024 * 1024
    domain_rate_per_minute: int = 30
    console_api_key: str = ""
    public_api_key: str = ""
    # radar response cache in Redis (PERF-2); on in compose, off for tests and host dev
    radar_cache: bool = False
    claude_cli: str = "claude"
    digest_model: str = "opus"
    digest_timeout_seconds: int = 900
    agy_cli: str = "agy"
    card_agy_model: str = "gemini-3.8-flash-low"
    card_agy_min_weekly: int = 10
    card_agy_min_five_hour: int = 2
    card_agy_batch: int = 100
    card_agy_parallel: int = 3
    # Codex first, then Antigravity, each down to its reserve, then local Qwen (2026-10-05)
    codex_cli: str = "codex"  # launchd has no nvm on PATH: set CODEX_CLI to the native binary
    codex_home: str = ""  # default ~/.codex (session files hold the rate-limit snapshot)
    card_codex_enabled: bool = True
    card_codex_model: str = ""  # the account's default Codex model
    card_codex_batch: int = 40
    card_codex_parallel: int = 2
    card_qwen_batch: int = 5
    card_qwen_fallback: bool = True  # after Codex and Antigravity are down to their reserves
    # Qwen full time (2026-10-06, user request): its lanes run next to Codex/Antigravity too
    card_qwen_alongside: bool = True
    card_qwen_parallel: int = 2
    card_unvalidated_daily_cap: int = 40  # cards per non-active source per 24 hours (2026-10-05)
    card_timeout_seconds: int = 300
    card_time_budget_seconds: int = 540


@lru_cache
def get_settings() -> Settings:
    return Settings()
