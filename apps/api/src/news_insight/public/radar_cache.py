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
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel

from news_insight import __version__
from news_insight.public.filters import ReaderFilters
from news_insight.public.periods import Window
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

log = logging.getLogger(__name__)
OPEN_TTL = 15 * 60
CLOSED_TTL = 24 * 3600
PREFIX = "radar:v1"


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
    return f"{PREFIX}:{__version__}:{TAXONOMY_REVISION}:{kind}:{digest}"


def ttl_for(window: Window, now: datetime) -> int:
    return OPEN_TTL if window.end > now else CLOSED_TTL


def cache_client() -> object | None:
    """The Redis client when the radar cache is enabled (settings.radar_cache)."""
    from news_insight.config import get_settings

    if not get_settings().radar_cache:
        return None
    from news_insight.scheduling.redis_guards import get_redis

    return get_redis()


def cached_json[M: BaseModel](
    key: str, ttl: int, compute: Callable[[], M], *, client: object | None
) -> tuple[str, bool]:
    """(JSON body, served from cache). Without a client, or on a cache outage, compute."""
    if client is None:
        return compute().model_dump_json(), False
    try:
        hit = client.get(key)  # type: ignore[attr-defined]
        if hit:
            return (hit.decode() if isinstance(hit, bytes) else str(hit)), True
    except Exception:  # noqa: BLE001
        log.warning("radar cache unavailable", exc_info=True)
    body = compute().model_dump_json()
    try:
        client.set(key, body, ex=ttl)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        log.debug("radar cache write failed", exc_info=True)
    return body, False


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
