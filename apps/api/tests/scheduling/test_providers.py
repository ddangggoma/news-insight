import pytest
import redis

from news_insight.scheduling.providers import PROVIDERS, ProviderGate, min_interval, provider_host

pytestmark = pytest.mark.redis


def test_shared_api_hosts_are_recognised() -> None:
    assert provider_host("https://api.openalex.org/works?search=x") == "api.openalex.org"
    assert provider_host("https://API.crossref.org/works") == "api.crossref.org"
    assert provider_host("https://www.example.com/feed") is None
    assert min_interval("https://api.openalex.org/works") == 86_400
    assert min_interval("https://www.example.com/feed") == 0


def test_one_budget_for_every_source_on_a_provider(redis_client: redis.Redis) -> None:
    now = [1000.0]
    gate = ProviderGate(redis_client, clock=lambda: now[0])
    burst = PROVIDERS["api.openalex.org"].burst

    assert [gate.try_acquire("api.openalex.org") for _ in range(burst + 1)] == [True] * burst + [
        False
    ]
    assert gate.try_acquire("api.crossref.org")  # another provider, another bucket
    now[0] += gate.wait_seconds("api.openalex.org")
    assert gate.try_acquire("api.openalex.org")


def test_back_off_keeps_the_longest_wait(redis_client: redis.Redis) -> None:
    gate = ProviderGate(redis_client)

    gate.back_off("api.openalex.org", 44_947)  # OpenAlex Retry-After until its daily reset
    gate.back_off("api.openalex.org", 60)

    assert 44_900 < gate.backoff_seconds("api.openalex.org") <= 44_947
    assert gate.backoff_seconds("api.crossref.org") == 0
