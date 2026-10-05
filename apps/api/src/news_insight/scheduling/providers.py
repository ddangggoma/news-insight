"""Shared API providers: one budget and one back-off for every source on the same API.

Seventy-odd OpenAlex search sources and nine Crossref ones were polled and validated as if
each had the API to itself (2026-10-05): OpenAlex now meters an unauthenticated client at
1,000 credits a day (a search costs 10) and Crossref's public pool allows one request a
second, so 47 candidates failed validation with HTTP 429. Collection and validation now draw
from one token bucket per provider, and a 429 with Retry-After pauses the whole provider.
"""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import redis

from news_insight.scheduling.redis_guards import TOKEN_BUCKET


@dataclass(frozen=True)
class Provider:
    per_day: float  # sustained requests per day
    burst: int  # requests allowed back to back
    validate_per_batch: int  # candidates per auto-validation batch
    min_interval_seconds: int = 0  # floor on each source's poll interval


PROVIDERS: dict[str, Provider] = {
    # 1,000 credits a day without a key, 10 per search: about 90 searches, a tenth kept back
    # and each search source polls once a day (76 sources on 2026-10-05)
    "api.openalex.org": Provider(
        per_day=90, burst=3, validate_per_batch=2, min_interval_seconds=24 * 3600
    ),
    # public pool 1 request/s (polite pool with mailto is more); stay well under it
    "api.crossref.org": Provider(per_day=30 * 60 * 24, burst=1, validate_per_batch=5),
}
MAX_BACKOFF_SECONDS = 24 * 3600


def provider_host(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    return host if host in PROVIDERS else None


def min_interval(url: str) -> int:
    host = provider_host(url)
    return PROVIDERS[host].min_interval_seconds if host else 0


class ProviderGate:
    """Token bucket and back-off flag per provider host, in Redis."""

    def __init__(
        self,
        client: redis.Redis,
        *,
        clock: Callable[[], float] | None = None,
        prefix: str = "provider:",
    ) -> None:
        import time

        self._client = client
        self._clock = clock or time.time
        self._prefix = prefix
        self._bucket = client.register_script(TOKEN_BUCKET)

    def backoff_seconds(self, host: str) -> int:
        ttl = self._client.ttl(f"{self._prefix}backoff:{host}")
        return int(ttl) if isinstance(ttl, int) and ttl > 0 else 0

    def back_off(self, host: str, seconds: int) -> None:
        seconds = max(1, min(int(seconds), MAX_BACKOFF_SECONDS))
        key = f"{self._prefix}backoff:{host}"
        current = self.backoff_seconds(host)
        if seconds > current:
            self._client.set(key, "1", ex=seconds)

    def try_acquire(self, host: str) -> bool:
        provider = PROVIDERS[host]
        allowed = self._bucket(
            keys=[f"{self._prefix}bucket:{host}"],
            args=[provider.burst, provider.per_day / 86400, self._clock()],
        )
        return bool(allowed == 1)

    def wait_seconds(self, host: str) -> int:
        """Time until the next token at the sustained rate."""
        return max(60, int(86400 / PROVIDERS[host].per_day))
