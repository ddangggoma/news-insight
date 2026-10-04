from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from news_insight.public.periods import (
    PeriodError,
    calendar_window,
    current_key,
    rolling_window,
    trailing_windows,
)

KST = ZoneInfo("Asia/Seoul")


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


def test_day_window_is_a_kst_calendar_day() -> None:
    window = calendar_window("day", "2026-10-04")
    assert window.start == kst(2026, 10, 4)
    assert window.end == kst(2026, 10, 5)
    assert window.prev_key == "2026-10-03"
    assert window.next_key == "2026-10-05"


def test_week_window_starts_on_monday() -> None:
    window = calendar_window("week", "2026-W40")
    assert window.start == kst(2026, 9, 28)
    assert window.end == kst(2026, 10, 5)
    assert window.prev_key == "2026-W39"
    assert window.next_key == "2026-W41"


def test_week_window_crosses_the_year_boundary() -> None:
    # ISO 2026 has 53 weeks; week 1 of 2027 starts on Monday 2027-01-04
    assert calendar_window("week", "2026-W53").next_key == "2027-W01"
    assert calendar_window("week", "2027-W01").start == kst(2027, 1, 4)
    assert calendar_window("week", "2027-W01").prev_key == "2026-W53"


def test_month_and_quarter_windows() -> None:
    month = calendar_window("month", "2026-12")
    assert (month.start, month.end) == (kst(2026, 12, 1), kst(2027, 1, 1))
    assert (month.prev_key, month.next_key) == ("2026-11", "2027-01")
    quarter = calendar_window("quarter", "2026-Q4")
    assert (quarter.start, quarter.end) == (kst(2026, 10, 1), kst(2027, 1, 1))
    assert (quarter.prev_key, quarter.next_key) == ("2026-Q3", "2027-Q1")


def test_previous_window_has_the_same_kind() -> None:
    window = calendar_window("month", "2026-03")
    assert window.previous().start == kst(2026, 2, 1)
    assert window.previous().end == kst(2026, 3, 1)


@pytest.mark.parametrize(
    ("kind", "key"),
    [
        ("day", "2026-13-01"),
        ("week", "2026-W54"),
        ("week", "2025-W53"),
        ("month", "2026-1"),
        ("quarter", "2026-Q5"),
        ("year", "2026"),
    ],
)
def test_invalid_keys_are_rejected(kind: str, key: str) -> None:
    with pytest.raises(PeriodError):
        calendar_window(kind, key)


def test_current_key_uses_kst() -> None:
    # 2026-10-04 23:30 UTC is already Monday 2026-10-05 in Seoul
    now = datetime(2026, 10, 4, 23, 30, tzinfo=UTC)
    assert current_key("day", now) == "2026-10-05"
    assert current_key("week", now) == "2026-W41"
    assert current_key("month", now) == "2026-10"
    assert current_key("quarter", now) == "2026-Q4"


def test_trailing_windows_end_with_the_given_window() -> None:
    # ISO 2025 has 52 weeks
    windows = trailing_windows(calendar_window("week", "2026-W02"), 4)
    assert [w.key for w in windows] == ["2025-W51", "2025-W52", "2026-W01", "2026-W02"]


def test_rolling_window_counts_back_from_now() -> None:
    now = datetime(2026, 10, 4, 12, tzinfo=UTC)
    window = rolling_window("7d", now)
    assert window.start == datetime(2026, 9, 27, 12, tzinfo=UTC)
    assert window.end == now
    assert window.previous().start == datetime(2026, 9, 20, 12, tzinfo=UTC)
    everything = rolling_window("all", now)
    assert everything.start is None
    with pytest.raises(PeriodError):
        rolling_window("2w", now)
