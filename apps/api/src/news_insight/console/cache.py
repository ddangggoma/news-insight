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
