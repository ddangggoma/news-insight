"""Redis-backed guards: per-domain token-bucket budgets and per-source collection locks."""

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Protocol

import redis

from news_insight.config import get_settings

_TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
tokens = math.min(capacity, tokens + math.max(0, now - ts) * refill)
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 60)
return allowed
"""

_RELEASE_IF_OWNER = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class RateLimiter(Protocol):
    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool: ...


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


class DomainRateLimiter:
    def __init__(
        self,
        client: redis.Redis,
        *,
        per_minute: int,
        clock: Callable[[], float] = time.time,
        prefix: str = "ratelimit:domain:",
    ) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._prefix = prefix
        self._script = client.register_script(_TOKEN_BUCKET)

    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        budget = per_minute or self._per_minute
        allowed = self._script(
            keys=[self._prefix + domain.lower()], args=[budget, budget / 60, self._clock()]
        )
        return bool(allowed == 1)


class SourceLock:
    def __init__(
        self, client: redis.Redis, *, ttl_seconds: int = 900, prefix: str = "lock:source:"
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._prefix = prefix
        self._release = client.register_script(_RELEASE_IF_OWNER)

    @contextmanager
    def hold(self, source_id: int | str) -> Iterator[bool]:
        """Yields whether the lock was taken; a name works as well as a source id."""
        key = f"{self._prefix}{source_id}"
        token = uuid.uuid4().hex
        acquired = bool(self._client.set(key, token, nx=True, ex=self._ttl))
        try:
            yield acquired
        finally:
            if acquired:
                self._release(keys=[key], args=[token])
