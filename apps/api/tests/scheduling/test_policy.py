import pytest

from news_insight.scheduling.policy import (
    POLL_RANGES,
    initial_interval,
    is_idle,
    next_interval,
    retry_delay,
)
from news_insight.sources.enums import PollClass

MIN = 60
HOUR = 3600


def test_ranges_match_requirements() -> None:
    assert POLL_RANGES == {
        PollClass.BREAKING: (5 * MIN, 15 * MIN),
        PollClass.NEWS: (15 * MIN, 60 * MIN),
        PollClass.COMMUNITY: (10 * MIN, 30 * MIN),
        PollClass.RESEARCH: (2 * HOUR, 2 * HOUR),
        PollClass.SLOW: (6 * HOUR, 24 * HOUR),
    }
    assert initial_interval(PollClass.NEWS) == 15 * MIN


def test_idle_polls_back_off_by_half_and_cap() -> None:
    assert next_interval(PollClass.NEWS, 900, idle=True, new_items=0) == 1350
    assert next_interval(PollClass.NEWS, 3000, idle=True, new_items=0) == 3600


def test_bursts_reset_to_the_fastest_interval() -> None:
    assert next_interval(PollClass.NEWS, 3600, idle=False, new_items=5) == 900


def test_some_new_items_shrink_towards_the_floor() -> None:
    assert next_interval(PollClass.NEWS, 3600, idle=False, new_items=2) == 2400
    assert next_interval(PollClass.NEWS, 1000, idle=False, new_items=1) == 900


def test_research_interval_is_fixed() -> None:
    assert next_interval(PollClass.RESEARCH, 7200, idle=True, new_items=0) == 7200
    assert next_interval(PollClass.RESEARCH, 7200, idle=False, new_items=9) == 7200


def test_idle_means_not_modified_or_nothing_new() -> None:
    assert is_idle(not_modified=True, new_items=3, updated_items=0) is True
    assert is_idle(not_modified=False, new_items=0, updated_items=0) is True
    assert is_idle(not_modified=False, new_items=0, updated_items=1) is False


def test_retry_delays_double_up_to_three_retries() -> None:
    assert [retry_delay(attempt) for attempt in (1, 2, 3)] == [60, 120, 240]
    with pytest.raises(ValueError):
        retry_delay(4)
