"""One story writer at a time (2026-10-05 audit: overlapping `stories.cluster` runs and the
multilingual merge deadlocked three times and inserted the same LSH rows twice)."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from news_insight.scheduling.redis_guards import SourceLock, get_redis

LOCK_SECONDS = 1800


@contextmanager
def story_writer(name: str = "stories") -> Iterator[bool]:
    """Yields False when another story writer holds the lock. If Redis cannot be reached the
    caller proceeds unlocked (a warning is logged) rather than stopping clustering."""
    try:
        lock = SourceLock(get_redis(), ttl_seconds=LOCK_SECONDS, prefix="lock:")
        held = lock.hold(name)
        acquired = held.__enter__()
    except Exception:  # noqa: BLE001 - Redis down must not stop clustering
        logging.getLogger(__name__).warning("story lock unavailable; running unlocked")
        yield True
        return
    try:
        yield acquired
    finally:
        held.__exit__(None, None, None)
