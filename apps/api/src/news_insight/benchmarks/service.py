"""The daily collection of the four leaderboards into snapshots and score rows."""

import hashlib
import json
import logging
from datetime import datetime
from types import ModuleType

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.names import resolve_model
from news_insight.benchmarks.sources import (
    BenchmarkError,
    SiteSnapshot,
    artificial_analysis,
    deepswe,
    livebench,
    lmarena,
)
from news_insight.net.safe_fetch import SafeFetcher

logger = logging.getLogger(__name__)

SOURCES: tuple[ModuleType, ...] = (deepswe, livebench, lmarena, artificial_analysis)
SAVED = "saved"
UNCHANGED = "unchanged"
UNEXPECTED = "error"


def raw_digest(raw: dict[str, object]) -> str:
    """sha256 of the raw payload as sorted JSON: the same data in another key order is the same."""
    text = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def collect_all(session: Session, fetcher: SafeFetcher, now: datetime) -> dict[str, str]:
    """Per site: "saved", "unchanged", or the error code (selector_drift, http_error,
    config_error, error). A site that fails keeps its last good snapshot and never blocks the
    others."""
    results: dict[str, str] = {}
    for module in SOURCES:
        site: str = module.SITE
        try:
            snapshot = module.fetch(fetcher, now)
            with session.begin_nested():
                results[site] = save(session, snapshot, now)
        except BenchmarkError as exc:
            logger.warning("benchmark %s: %s (%s)", site, exc.code, exc)
            results[site] = exc.code
        except Exception:  # noqa: BLE001 - one site's bug must not stop the others
            logger.exception("benchmark %s failed", site)
            results[site] = UNEXPECTED
    return results


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
