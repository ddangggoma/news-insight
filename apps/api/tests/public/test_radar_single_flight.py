import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel

from news_insight.public import radar_cache


class Body(BaseModel):
    value: int


class FakeRedis:
    """The few Redis calls cached_json makes, thread-safe like the real client."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self.lock:
            return self.data.get(key)

    def set(self, key: str, value: str, *, ex: int, nx: bool = False) -> bool:
        with self.lock:
            if nx and key in self.data:
                return False
            self.data[key] = value
            return True

    def exists(self, key: str) -> int:
        with self.lock:
            return int(key in self.data)

    def delete(self, key: str) -> None:
        with self.lock:
            self.data.pop(key, None)


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(radar_cache, "FILL_POLL_SECONDS", 0.01)


def test_concurrent_misses_compute_the_view_once() -> None:
    client = FakeRedis()
    calls: list[int] = []

    def compute() -> Body:
        calls.append(1)
        time.sleep(0.2)
        return Body(value=7)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(lambda _: radar_cache.cached_json("k", 60, compute, client=client), range(6))
        )

    assert len(calls) == 1
    assert {body for body, _ in results} == {'{"value":7}'}
    assert sorted(hit for _, hit in results) == [False, True, True, True, True, True]
    assert client.exists("k:filling") == 0


def test_a_failed_fill_releases_the_lock_so_the_next_request_computes() -> None:
    client = FakeRedis()

    def broken() -> Body:
        raise RuntimeError("database went away")

    with pytest.raises(RuntimeError):
        radar_cache.cached_json("k", 60, broken, client=client)

    assert client.exists("k:filling") == 0
    assert radar_cache.cached_json("k", 60, lambda: Body(value=1), client=client) == (
        '{"value":1}',
        False,
    )


def test_a_waiter_computes_itself_when_the_fill_outlives_the_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedis()
    client.set("k:filling", "1", ex=60)  # a fill that never finishes
    monkeypatch.setattr(radar_cache, "FILL_WAIT_SECONDS", 0.05)

    assert radar_cache.cached_json("k", 60, lambda: Body(value=3), client=client) == (
        '{"value":3}',
        False,
    )


def test_warm_keeps_closed_windows_and_recomputes_open_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from news_insight.public import radar

    computed: list[tuple[str, str]] = []

    def fake_radar(session: object, filters: object, window: object, key: str, now: object) -> Body:
        computed.append((window.kind, window.key))  # type: ignore[attr-defined]
        return Body(value=len(computed))

    monkeypatch.setattr(radar, "radar", fake_radar)
    client = FakeRedis()
    now = datetime(2026, 10, 29, 14, tzinfo=UTC)

    assert radar_cache.warm(None, now=now, client=client) == 12
    computed.clear()
    # 2026-10-29: 12 views every run took 25 minutes; the six closed ones stay cached
    assert radar_cache.warm(None, now=now, client=client) == 6
    current = {kind: key for kind, key in computed}
    assert len(computed) == 6 and set(current) == {"week", "month", "quarter"}
