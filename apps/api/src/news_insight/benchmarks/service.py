"""The daily collection of the leaderboards into snapshots and score rows."""

import hashlib
import json
import logging
from datetime import datetime
from types import ModuleType
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.names import resolve_model
from news_insight.benchmarks.sources import (
    BenchmarkError,
    NotModified,
    SiteSnapshot,
    artificial_analysis,
    deepswe,
    epoch,
    livebench,
    lmarena,
    osworld,
    tau2,
    terminal_bench,
)
from news_insight.net.safe_fetch import SafeFetcher

logger = logging.getLogger(__name__)

SOURCES: tuple[ModuleType, ...] = (
    deepswe,
    livebench,
    lmarena,
    artificial_analysis,
    terminal_bench,
    epoch,
    osworld,
    tau2,
)
SAVED = "saved"
UNCHANGED = "unchanged"
UNEXPECTED = "error"


def raw_digest(raw: dict[str, object]) -> str:
    """sha256 of the raw payload as sorted JSON: the same data in another key order is the same."""
    text = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _latest(session: Session, site: str) -> BenchmarkSnapshot | None:
    return session.scalars(
        select(BenchmarkSnapshot)
        .where(BenchmarkSnapshot.site == site)
        .order_by(BenchmarkSnapshot.fetched_at.desc(), BenchmarkSnapshot.id.desc())
        .limit(1)
    ).first()


def _fetch(
    module: ModuleType, fetcher: SafeFetcher, now: datetime, previous: dict[str, Any] | None
) -> SiteSnapshot:
    if getattr(module, "USES_PREVIOUS", False):
        snapshot: SiteSnapshot = module.fetch(fetcher, now, previous)
    else:
        snapshot = module.fetch(fetcher, now)
    return snapshot


def collect_all(session: Session, fetcher: SafeFetcher, now: datetime) -> dict[str, str]:
    """Per site: "saved", "unchanged", or the error code (selector_drift, http_error,
    config_error, parse_error, error). A site that fails keeps its last good snapshot and never
    blocks the others. Each site is fetched with no transaction open and committed on its own,
    so a slow site holds nothing idle and a restart keeps the sites already saved. A site that
    reads its previous snapshot (an ETag, per-file SHAs) gets it first; when it answers
    NotModified that snapshot is marked seen today."""
    results: dict[str, str] = {}
    for module in SOURCES:
        site: str = module.SITE
        try:
            previous = None
            if getattr(module, "USES_PREVIOUS", False):
                latest = _latest(session, site)
                previous = latest.raw if latest is not None else None
                session.commit()  # no transaction stays open while the site is fetched
            try:
                snapshot = _fetch(module, fetcher, now, previous)
            except NotModified:
                with session.begin_nested():
                    latest = _latest(session, site)
                    if latest is not None:
                        latest.fetched_at = now
                session.commit()
                results[site] = UNCHANGED
                continue
            with session.begin_nested():
                results[site] = save(session, snapshot, now)
            session.commit()
        except BenchmarkError as exc:
            logger.warning("benchmark %s: %s (%s)", site, exc.code, exc)
            results[site] = exc.code
        except Exception:  # noqa: BLE001 - one site's bug must not stop the others
            logger.exception("benchmark %s failed", site)
            session.rollback()
            results[site] = UNEXPECTED
    return results


def fetch_only(
    fetcher: SafeFetcher, now: datetime, sites: list[str] | None = None
) -> dict[str, SiteSnapshot | str]:
    """Each site's snapshot fetched and parsed but never saved (`collect --dry-run`); a site
    that fails gives its error code instead. No database is touched."""
    out: dict[str, SiteSnapshot | str] = {}
    for module in SOURCES:
        site: str = module.SITE
        if sites and site not in sites:
            continue
        try:
            out[site] = _fetch(module, fetcher, now, None)
        except NotModified:  # pragma: no cover - nothing to compare against without a database
            out[site] = UNCHANGED
        except BenchmarkError as exc:
            logger.warning("benchmark %s: %s (%s)", site, exc.code, exc)
            out[site] = exc.code
        except Exception:  # noqa: BLE001 - one site's bug must not stop the others
            logger.exception("benchmark %s failed", site)
            out[site] = UNEXPECTED
    return out


def save(session: Session, snapshot: SiteSnapshot, now: datetime) -> str:
    digest = raw_digest(snapshot.raw)
    existing = session.scalar(
        select(BenchmarkSnapshot).where(
            BenchmarkSnapshot.site == snapshot.site, BenchmarkSnapshot.sha256 == digest
        )
    )
    if existing is not None:
        # the same bytes again: no new rows, but the site was seen today (staleness alert) and,
        # if it went back to an older state, this snapshot is the current one again
        existing.fetched_at = now
        return UNCHANGED
    row = BenchmarkSnapshot(
        site=snapshot.site,
        release=snapshot.release,
        fetched_at=now,
        sha256=digest,
        raw=snapshot.raw,
    )
    session.add(row)
    session.flush()
    matched: dict[str, int | None] = {}
    for score in snapshot.rows:
        if score.model_raw not in matched:
            matched[score.model_raw] = resolve_model(session, score.model_raw, score.org)
        session.add(
            BenchmarkScore(
                snapshot_id=row.id,
                site=snapshot.site,
                board=score.board,
                model_raw=score.model_raw,
                model_id=matched[score.model_raw],
                org=score.org,
                config=score.config,
                metric=score.metric,
                value=score.value,
                ci_low=score.ci_low,
                ci_high=score.ci_high,
                extra=score.extra,
            )
        )
    session.flush()
    return SAVED
