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


def test_stale_answer_is_served_while_a_refresh_runs() -> None:
    import threading
    import time as clock

    from news_insight.console.cache import cached_stale, clear

    clear()
    calls: list[int] = []
    release = threading.Event()

    def compute() -> int:
        calls.append(1)
        if len(calls) > 1:
            release.wait(2)
        return len(calls)

    assert cached_stale("k", 1, compute) == 1  # first request computes
    clock.sleep(1.05)
    assert cached_stale("k", 1, compute) == 1  # expired: old answer at once, refresh starts
    release.set()
    for _ in range(50):
        if cached_stale("k", 1, compute) == 2:
            break
        clock.sleep(0.02)
    assert cached_stale("k", 1, compute) == 2 and len(calls) == 2
    clear()
