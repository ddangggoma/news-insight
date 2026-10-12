"""Radar response cache (checklist PERF-2, plan 08 B6).

The radar aggregates eight windows of the corpus per request. Responses are cached in Redis
under the parsed view (window, scope, filters), not the raw query string, so the warm-up task
and readers share entries. Closed windows never change and live a day; the current window
lives 15 minutes. Filtered views are cached on demand the same way.
"""

import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from news_insight import __version__
from news_insight.public.filters import ReaderFilters
from news_insight.public.periods import Window
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

log = logging.getLogger(__name__)
OPEN_TTL = 15 * 60
CLOSED_TTL = 24 * 3600
PREFIX = "radar:v1"
# single-flight fill: the computing request holds a lock this long at most; others poll for
# its result up to FILL_WAIT_SECONDS (the slowest radar view takes about 15 s cold)
FILL_LOCK_SECONDS = 60
FILL_WAIT_SECONDS = 30.0
FILL_POLL_SECONDS = 0.2


def _code_hash() -> str:
    """Hash of the reader query code: a deploy that changes rules, statistics or the response
    shape starts new keys even when the package version stays the same."""
    digest = hashlib.sha1()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


CODE_HASH = _code_hash()


def view_key(
    kind: str, window: Window, filters: ReaderFilters, extra: dict[str, str] | None = None
) -> str:
    view = {
        "w": [window.kind, window.key],
        "scope": filters.scope,
        "values": {axis: sorted(values) for axis, values in sorted(filters.values.items())},
        "q": filters.q,
        **(extra or {}),
    }
    digest = hashlib.sha1(json.dumps(view, sort_keys=True).encode()).hexdigest()[:20]
    return f"{PREFIX}:{__version__}:{CODE_HASH}:{TAXONOMY_REVISION}:{kind}:{digest}"


def ttl_for(window: Window, now: datetime) -> int:
    return OPEN_TTL if window.end > now else CLOSED_TTL


def cache_client() -> object | None:
    """The Redis client when the radar cache is enabled (settings.radar_cache)."""
    from news_insight.config import get_settings

    if not get_settings().radar_cache:
        return None
    from news_insight.scheduling.redis_guards import get_redis

    return get_redis()


def _get(client: object, key: str) -> str | None:
    hit = client.get(key)  # type: ignore[attr-defined]
    if not hit:
        return None
    return hit.decode() if isinstance(hit, bytes) else str(hit)


def _wait_for(client: object, key: str, lock: str) -> str | None:
    """Poll for the entry another request is computing; None once its lock is gone or expired."""
    deadline = time.monotonic() + FILL_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(FILL_POLL_SECONDS)
        body = _get(client, key)
        if body is not None:
            return body
        if not client.exists(lock):  # type: ignore[attr-defined]
            return _get(client, key)
    return None


def cached_json[M: BaseModel](
    key: str, ttl: int, compute: Callable[[], M], *, client: object | None
) -> tuple[str, bool]:
    """(JSON body, served from cache). Without a client, or on a cache outage, compute.

    One request computes a missing entry (2026-10-12): a Redis lock marks the fill in progress,
    and concurrent requests for the same view wait for that result instead of running the same
    corpus-wide aggregate side by side. A waiter that gives up computes on its own.
    """
    if client is None:
        return compute().model_dump_json(), False
    lock = f"{key}:filling"
    owner = False
    try:
        body = _get(client, key)
        if body is not None:
            return body, True
        owner = bool(client.set(lock, "1", nx=True, ex=FILL_LOCK_SECONDS))  # type: ignore[attr-defined]
        if not owner:
            body = _wait_for(client, key, lock)
            if body is not None:
                return body, True
    except Exception:  # noqa: BLE001
        log.warning("radar cache unavailable", exc_info=True)
    try:
        body = compute().model_dump_json()
        try:
            client.set(key, body, ex=ttl)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            log.debug("radar cache write failed", exc_info=True)
        return body, False
    finally:
        if owner:
            with contextlib.suppress(Exception):
                client.delete(lock)  # type: ignore[attr-defined]


def warm(session: object, *, now: datetime, client: object) -> int:
    """Pre-compute the default radar views (week, month, quarter; current and previous window;
    DX-relevant and all scopes) so the first reader after a cache expiry is not kept waiting."""
    from news_insight.public import radar as radar_queries
    from news_insight.public.periods import calendar_window, current_key

    warmed = 0
    for kind in ("week", "month", "quarter"):
        current = calendar_window(kind, current_key(kind, now))
        for window in (current, current.previous()):
            for scope in ("relevant", "all"):
                filters = ReaderFilters.build(scope=scope, q=None)
                key = view_key("radar", window, filters)

                def compute(
                    w: Window = window, f: ReaderFilters = filters, current_key: str = current.key
                ) -> BaseModel:
                    return radar_queries.radar(session, f, w, current_key, now)  # type: ignore[arg-type]

                with contextlib.suppress(Exception):  # refresh even an unexpired entry
                    client.delete(key)  # type: ignore[attr-defined]
                cached_json(key, ttl_for(window, now), compute, client=client)
                warmed += 1
    return warmed
