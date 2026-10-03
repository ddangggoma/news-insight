"""Adaptive polling (requirements §4): health-driven intervals within per-class bounds."""

import math

from news_insight.sources.enums import PollClass

MINUTE = 60
HOUR = 3600
POLL_RANGES: dict[PollClass, tuple[int, int]] = {
    PollClass.BREAKING: (5 * MINUTE, 15 * MINUTE),
    PollClass.NEWS: (15 * MINUTE, 60 * MINUTE),
    PollClass.COMMUNITY: (10 * MINUTE, 30 * MINUTE),
    PollClass.RESEARCH: (2 * HOUR, 2 * HOUR),
    PollClass.SLOW: (6 * HOUR, 24 * HOUR),
}
IDLE_GROWTH = 1.5
BURST_THRESHOLD = 5
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 60


def initial_interval(poll_class: PollClass) -> int:
    return POLL_RANGES[poll_class][0]


def is_idle(*, not_modified: bool, new_items: int, updated_items: int) -> bool:
    return not_modified or new_items + updated_items == 0


def next_interval(poll_class: PollClass, current: int, *, idle: bool, new_items: int) -> int:
    low, high = POLL_RANGES[poll_class]
    if new_items >= BURST_THRESHOLD:
        return low
    if idle:
        candidate = math.ceil(current * IDLE_GROWTH)
    elif new_items > 0:
        candidate = math.floor(current / IDLE_GROWTH)
    else:
        candidate = current
    return max(low, min(high, candidate))


def retry_delay(attempt: int) -> int:
    """Delay before retry number `attempt` (1-based): 60 s, 120 s, 240 s."""
    if not 1 <= attempt <= MAX_RETRIES:
        raise ValueError(f"retry attempt must be 1..{MAX_RETRIES}, got {attempt}")
    return RETRY_BASE_SECONDS * (1 << (attempt - 1))
