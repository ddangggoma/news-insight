"""A short in-process cache for heavy console aggregates (2026-10-08).

The card stats scan every card several times (1-2 s on the live database) and the dashboard
asks on each visit. `CONSOLE_CACHE_SECONDS` (60 in compose, 0 = off in tests and host dev)
keeps a computed answer that long; numbers on the console may lag by that much.

Concurrent misses on one key compute once (2026-10-12): the others wait for that answer instead
of each starting the same scan, which is how a burst of reloads used to pile up on the database.
"""

import threading
import time
from collections.abc import Callable

_store: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
_key_locks: dict[str, threading.Lock] = {}


def _fresh(key: str, seconds: int) -> tuple[bool, object]:
    with _lock:
        hit = _store.get(key)
    if hit is not None and time.monotonic() - hit[0] < seconds:
        return True, hit[1]
    return False, None


def cached[T](key: str, seconds: int, compute: Callable[[], T]) -> T:
    if seconds <= 0:
        return compute()
    found, value = _fresh(key, seconds)
    if found:
        return value  # type: ignore[return-value]
    with _lock:
        key_lock = _key_locks.setdefault(key, threading.Lock())
    with key_lock:
        # another request may have filled the entry while this one waited
        found, value = _fresh(key, seconds)
        if found:
            return value  # type: ignore[return-value]
        computed = compute()
        with _lock:
            _store[key] = (time.monotonic(), computed)
        return computed


def clear() -> None:
    with _lock:
        _store.clear()
