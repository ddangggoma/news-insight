"""Reader cache of the 연구 and 특허 views (plan 19 §4), in Redis whatever settings.radar_cache
says: Redis is always there for Celery, and these views read up to the counts' as_of, so they
change only when the nightly job builds a new day (as_of moves to it and the keys with it) or
late cards and patents arrive. Entries live CACHE_TTL; the nightly job warms the default views
(2 menus × 3 periods × 5 tabs, documents page 1) right after building the counts.

The key holds the view (as_of and every query parameter), the package version, the taxonomy
revision and a hash of the code that computes it (public, insights, research, patents), so a
deploy that changes a rule or the response shape starts new keys."""

import dataclasses
import hashlib
import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from news_insight import __version__
from news_insight.public import domains
from news_insight.public.patents import PatentDomain
from news_insight.public.radar_cache import cached_json, plain_key
from news_insight.public.research import ResearchDomain
from news_insight.taxonomy.catalog import TAXONOMY_REVISION

log = logging.getLogger(__name__)
CACHE_TTL = 6 * 3600
PREFIX = "domain:v1"
TABS: tuple[domains.Tab, ...] = ("overview", "fields", "companies", "trends", "documents")
PERIODS: tuple[domains.Period, ...] = ("week", "month", "quarter")
_PACKAGE = Path(__file__).resolve().parents[1]


def _code_hash() -> str:
    digest = hashlib.sha1()
    for folder in ("public", "insights", "research", "patents"):
        for path in sorted((_PACKAGE / folder).glob("*.py")):
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


CODE_HASH = _code_hash()


def cache_client() -> object | None:
    """The Redis client (a dependency, so tests can swap it)."""
    from news_insight.scheduling.redis_guards import get_redis

    try:
        return get_redis()
    except Exception:  # noqa: BLE001 - a bad URL: serve uncached
        log.warning("domain cache unavailable", exc_info=True)
        return None


def view_key(domain: domains.Domain, as_of: object, query: domains.Query) -> str:
    view = {"as_of": str(as_of), **dataclasses.asdict(query)}
    return plain_key(f"{PREFIX}:{__version__}:{CODE_HASH}:{TAXONOMY_REVISION}:{domain.name}", view)


def serve(
    session: Session,
    domain: domains.Domain,
    query: domains.Query,
    *,
    now: datetime,
    client: object | None,
) -> tuple[str, bool]:
    """(JSON body, served from cache). Unknown field or company raise before anything is
    stored (domains.UnknownField, domains.UnknownCompany)."""
    built = domains.stats_range(session)
    as_of = domains.as_of(now, built)
    return cached_json(
        view_key(domain, as_of, query),
        CACHE_TTL,
        lambda: domains.build_view(session, domain, query, now=now, built=built),
        client=client,
    )


def default_views() -> Iterator[tuple[domains.Domain, domains.Query]]:
    for domain in (ResearchDomain(), PatentDomain()):
        for period in PERIODS:
            for tab in TABS:
                yield (
                    domain,
                    domains.Query(
                        tab=tab,
                        period=period,
                        field=None,
                        company=None,
                        org=None,
                        kind="company",
                        page=1,
                    ),
                )


def warm(session: Session, *, now: datetime, client: object) -> int:
    """Compute the default views again (dropping any entry of the same as_of first)."""
    built = domains.stats_range(session)
    as_of = domains.as_of(now, built)
    warmed = 0
    for domain, query in default_views():
        key = view_key(domain, as_of, query)
        try:
            client.delete(key)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            log.warning("domain cache unavailable", exc_info=True)
            return warmed

        def compute(d: domains.Domain = domain, q: domains.Query = query) -> domains.DomainView:
            return domains.build_view(session, d, q, now=now, built=built)

        cached_json(key, CACHE_TTL, compute, client=client)
        warmed += 1
    return warmed
