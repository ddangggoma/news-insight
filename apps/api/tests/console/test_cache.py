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
