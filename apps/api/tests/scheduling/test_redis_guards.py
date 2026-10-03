import pytest
import redis

from news_insight.scheduling.redis_guards import DomainRateLimiter, SourceLock

pytestmark = pytest.mark.redis


def test_allows_the_budget_then_denies(redis_client: redis.Redis) -> None:
    limiter = DomainRateLimiter(redis_client, per_minute=3, clock=lambda: 1000.0)

    assert [limiter.try_acquire("example.com") for _ in range(4)] == [True, True, True, False]


def test_budget_refills_over_time(redis_client: redis.Redis) -> None:
    now = [1000.0]
    limiter = DomainRateLimiter(redis_client, per_minute=60, clock=lambda: now[0])
    for _ in range(60):
        assert limiter.try_acquire("example.com")
    assert limiter.try_acquire("example.com") is False

    now[0] += 1.0

    assert limiter.try_acquire("example.com") is True


def test_domains_have_independent_budgets(redis_client: redis.Redis) -> None:
    limiter = DomainRateLimiter(redis_client, per_minute=1, clock=lambda: 1000.0)

    assert limiter.try_acquire("a.example.com") is True
    assert limiter.try_acquire("a.example.com") is False
    assert limiter.try_acquire("b.example.com") is True


def test_per_call_budget_override(redis_client: redis.Redis) -> None:
    limiter = DomainRateLimiter(redis_client, per_minute=1, clock=lambda: 1000.0)

    assert limiter.try_acquire("example.com", per_minute=2) is True
    assert limiter.try_acquire("example.com", per_minute=2) is True
    assert limiter.try_acquire("example.com", per_minute=2) is False


def test_source_lock_is_exclusive(redis_client: redis.Redis) -> None:
    lock = SourceLock(redis_client)

    with lock.hold(1) as first, lock.hold(1) as second, lock.hold(2) as other:
        assert (first, second, other) == (True, False, True)


def test_source_lock_is_released_after_use(redis_client: redis.Redis) -> None:
    lock = SourceLock(redis_client)
    with lock.hold(1) as acquired:
        assert acquired

    with lock.hold(1) as again:
        assert again
