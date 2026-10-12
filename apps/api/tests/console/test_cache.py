import time
from concurrent.futures import ThreadPoolExecutor

from news_insight.console.cache import cached, clear


def test_cached_keeps_a_value_for_its_lifetime_and_off_means_always_fresh() -> None:
    clear()
    calls: list[int] = []

    def compute() -> int:
        calls.append(1)
        return len(calls)

    assert cached("k", 60, compute) == 1
    assert cached("k", 60, compute) == 1
    assert cached("k", 0, compute) == 2 and cached("k", 0, compute) == 3
    clear()
    assert cached("k", 60, compute) == 4


def test_concurrent_misses_compute_once() -> None:
    clear()
    calls: list[int] = []

    def compute() -> int:
        calls.append(1)
        time.sleep(0.2)
        return 42

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cached("slow", 60, compute), range(8)))

    assert results == [42] * 8
    assert len(calls) == 1
