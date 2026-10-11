"""A short in-process cache for heavy console aggregates (2026-10-08).

The card stats scan every card several times (1-2 s on the live database) and the dashboard
asks on each visit. `CONSOLE_CACHE_SECONDS` (60 in compose, 0 = off in tests and host dev)
keeps a computed answer that long; numbers on the console may lag by that much.
"""

import threading
import time
from collections.abc import Callable

_store: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def cached[T](key: str, seconds: int, compute: Callable[[], T]) -> T:
    if seconds <= 0:
        return compute()
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
    if hit is not None and now - hit[0] < seconds:
        return hit[1]  # type: ignore[return-value]
    value = compute()
    with _lock:
        _store[key] = (time.monotonic(), value)
    return value


def clear() -> None:
    with _lock:
        _store.clear()


_refreshing: set[str] = set()


def cached_stale[T](key: str, seconds: int, compute: Callable[[], T]) -> T:
    """Like `cached`, but an expired answer is still returned at once while a background thread
    computes the next one (2026-10-11: the card progress page took 7-8 s under card runs).
    Only the very first request waits. `compute` must open its own database session."""
    if seconds <= 0:
        return compute()
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        stale = hit is not None and now - hit[0] >= seconds
        start = stale and key not in _refreshing
        if start:
            _refreshing.add(key)
    if hit is None:
        value = compute()
        with _lock:
            _store[key] = (time.monotonic(), value)
        return value
    if start:

        def refresh() -> None:
            try:
                fresh = compute()
                with _lock:
                    _store[key] = (time.monotonic(), fresh)
            finally:
                with _lock:
                    _refreshing.discard(key)

        threading.Thread(target=refresh, name=f"cache-{key}", daemon=True).start()
    return hit[1]  # type: ignore[return-value]
