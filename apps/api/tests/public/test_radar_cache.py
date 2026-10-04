from datetime import UTC, datetime

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.public import radar_cache
from news_insight.public.filters import ReaderFilters
from news_insight.public.periods import calendar_window
from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


@pytest.fixture
def corpus(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session)


def test_view_key_ignores_spelling_of_the_same_view() -> None:
    window = calendar_window("week", "2026-W40")
    a = ReaderFilters.build(scope="relevant", q=None, signal=["launch", "research"])
    b = ReaderFilters.build(scope="relevant", q=None, signal=["research", "launch", "launch"])
    c = ReaderFilters.build(scope="all", q=None, signal=["launch"])

    assert radar_cache.view_key("radar", window, a) == radar_cache.view_key("radar", window, b)
    assert radar_cache.view_key("radar", window, a) != radar_cache.view_key("radar", window, c)


def test_closed_windows_live_a_day_and_open_ones_fifteen_minutes() -> None:
    closed = calendar_window("week", "2026-W30")
    current = calendar_window("week", "2026-W40")
    now = datetime(2026, 10, 1, tzinfo=UTC)

    assert radar_cache.ttl_for(closed, now) == radar_cache.CLOSED_TTL
    assert radar_cache.ttl_for(current, now) == radar_cache.OPEN_TTL


def test_radar_is_served_from_cache_on_the_second_request(
    public_client: TestClient,
    public_headers: dict[str, str],
    redis_client: redis.Redis,
    corpus: dict[str, int],
) -> None:
    public_client.app.dependency_overrides[radar_cache.cache_client] = lambda: redis_client  # type: ignore[attr-defined]
    params = {"period": "week", "key": "2026-W40"}

    first = public_client.get("/api/public/radar", params=params, headers=public_headers)
    second = public_client.get("/api/public/radar", params=params, headers=public_headers)

    assert first.headers["x-cache"] == "miss" and second.headers["x-cache"] == "hit"
    assert first.json() == second.json() and first.json()["themes"]
