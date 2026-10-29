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
    openalex_api_key: str = ""  # free key: 10x the daily budget, sent as a header (in .env only)
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
    # operational alerts stay on the console (2026-10-09 user decision: no alert mail);
    # SMTP still sends sign-up notices to the admin
    ops_alert_mail: bool = False
    fetch_timeout_seconds: float = 15.0
    fetch_max_redirects: int = 3
    fetch_max_bytes: int = 5 * 1024 * 1024
    domain_rate_per_minute: int = 30
    console_api_key: str = ""
    public_api_key: str = ""
    # radar response cache in Redis (PERF-2); on in compose, off for tests and host dev
    radar_cache: bool = False
    # console aggregates (card stats, overview) kept this many seconds; 0 = off (tests, host dev)
    console_cache_seconds: int = 0
    # concurrent API requests admitted at once; the rest wait this long, then get 503 (overload.py)
    api_max_inflight: int = 0
    api_queue_seconds: float = 10.0
    claude_cli: str = "claude"
    digest_model: str = "opus"
    digest_timeout_seconds: int = 900
    # trend reports on request (plan 17 R1): written on the host with the Claude CLI
    report_model: str = "opus"
    report_timeout_seconds: int = 1500
    report_user_daily: int = 5  # admins are not capped per user
    report_site_daily: int = 20
    # spoken briefing (plan 13 A1): rendered on the host with macOS `say`, served by Caddy
    media_dir: str = "/srv/media"
    briefing_voice: str = "Yuna"
    briefing_voice_rate: int = 185
    agy_cli: str = "agy"
    card_agy_model: str = "gemini-3.8-flash-low"
    card_agy_min_weekly: int = 10
    card_agy_min_five_hour: int = 2
    card_agy_batch: int = 100
    card_agy_parallel: int = 3
    # Antigravity's Claude Sonnet after its Gemini models, down to the same 10 % weekly reserve
    # of its own "Claude and GPT models" limit (2026-10-29, user request). Measured that day:
    # 80 items in 102 s cost 5 % of the week and 10 % of five hours, 25 items 3 % and 6 % (the
    # instructions dominate small batches), so batches are large and the five-hour limit paces it
    card_agy_claude: bool = True
    card_agy_claude_model: str = "claude-sonnet-5-5-medium"
    card_agy_claude_batch: int = 100
    card_agy_claude_parallel: int = 2
    # Cards use Antigravity and Claude Haiku only (2026-10-13, user request): Codex and the local
    # Qwen are off by default. Codex stays available with CARD_CODEX_ENABLED, Qwen with
    # `cards run --qwen-only` or CARD_QWEN_FALLBACK.
    codex_cli: str = "codex"  # launchd has no nvm on PATH: set CODEX_CLI to the native binary
    codex_home: str = ""  # default ~/.codex (session files hold the rate-limit snapshot)
    card_codex_enabled: bool = False
    card_codex_model: str = ""  # the account's default Codex model
    card_codex_batch: int = 40
    card_codex_parallel: int = 2
    # Claude Code for cards: Haiku runs lanes next to Antigravity in every scheduled run and
    # carries on alone once Antigravity is down to its reserve (2026-10-13, user request).
    # Scheduled runs use it while `card_claude` is on (or before `card_claude_until`, ISO time),
    # outside the quiet hours (KST) and below a daily card cap (0: none); `cards run --claude`
    # ignores all three. Since 2026-10-29 (user request) there are no quiet hours and no cap:
    # every collected item gets a card, and Haiku stops only when Claude reports its limit.
    card_claude: bool = True
    card_claude_until: str = ""
    card_claude_model: str = "claude-haiku-5-5"
    card_claude_batch: int = 12
    card_claude_parallel: int = 8
    card_claude_quiet_hours: str = ""
    card_claude_daily_cap: int = 0
    card_qwen_batch: int = 5
    # Qwen for cards when Claude is not in the run (quiet hours, daily cap): off since
    # 2026-10-13; `card_qwen_alongside` also runs its lanes next to Antigravity
    card_qwen_fallback: bool = False
    card_qwen_alongside: bool = False
    card_qwen_parallel: int = 2
    card_unvalidated_daily_cap: int = 40  # cards per non-active source per 24 hours (2026-10-05)
    card_cap_bypass_dx: float = 0.5  # triage probability that passes that cap (2026-10-10)
    card_timeout_seconds: int = 300
    card_time_budget_seconds: int = 540


@lru_cache
def get_settings() -> Settings:
    return Settings()
