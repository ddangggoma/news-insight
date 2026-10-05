"""Celery entry points. They wire sessions, locks and fetchers; logic lives in services."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from news_insight.collect.dispatch import claim_due_sources
from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.content.retention import downsample_snapshots, purge_expired_bodies
from news_insight.db import session_scope
from news_insight.jobs.celery_app import celery_app
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.providers import ProviderGate
from news_insight.scheduling.redis_guards import DomainRateLimiter, SourceLock, get_redis
from news_insight.sources.autovalidate import auto_validate
from news_insight.sources.canary import run_canaries
from news_insight.sources.models import Source
from news_insight.sources.quality import run_quality
from news_insight.stories.service import cluster


@celery_app.task(name="collect.dispatch_due")
def dispatch_due() -> int:
    with session_scope() as session:
        source_ids = claim_due_sources(session, datetime.now(UTC))
    for source_id in source_ids:
        collect_source_task.delay(source_id)
    return len(source_ids)


@celery_app.task(name="collect.source")
def collect_source_task(source_id: int) -> str:
    settings = get_settings()
    client = get_redis()
    with SourceLock(client).hold(source_id) as acquired:
        if not acquired:
            return "locked"
        with session_scope() as session, SafeFetcher.from_settings(settings) as fetcher:
            source = session.get(Source, source_id)
            if source is None:
                return "missing"
            run = collect_source(
                session,
                source,
                fetcher=fetcher,
                limiter=DomainRateLimiter(client, per_minute=settings.domain_rate_per_minute),
                now=datetime.now(UTC),
                gate=ProviderGate(client),
            )
            return run.outcome.value


@celery_app.task(name="sources.run_canaries")
def run_canaries_task() -> int:
    with session_scope() as session:
        return len(run_canaries(session, datetime.now(UTC)))


AUTO_VALIDATE_BATCH = 100


@celery_app.task(name="sources.auto_validate")
def auto_validate_task() -> dict[str, Any]:
    with SafeFetcher.from_settings(get_settings()) as fetcher:
        stats = auto_validate(
            session_scope,
            fetcher=fetcher,
            now=datetime.now(UTC),
            limit=AUTO_VALIDATE_BATCH,
            gate=ProviderGate(get_redis()),
        )
    return asdict(stats)


@celery_app.task(name="stories.cluster")
def cluster_stories_task() -> dict[str, Any]:
    from news_insight.stories.lock import story_writer

    with story_writer() as acquired:
        if not acquired:
            return {"skipped": "another story writer is running"}
        return asdict(cluster(session_scope, now=datetime.now(UTC)))


@celery_app.task(name="sources.quality")
def source_quality_task() -> dict[str, Any]:
    with session_scope() as session:
        return asdict(run_quality(session, now=datetime.now(UTC)))


@celery_app.task(name="briefing.freeze")
def briefing_freeze_task() -> int:
    from news_insight.briefing.service import freeze
    from news_insight.signals.service import snapshot

    now = datetime.now(UTC)
    with session_scope() as session:
        today = now.astimezone(ZoneInfo(get_settings().timezone)).date()
        frozen = freeze(session, briefing_date=today, now=now)
        snapshot(session, day=today, now=now)  # PRD-1: the radar cards the 05:00 roles will read
        return len(frozen.candidate_ids)


@celery_app.task(name="content.purge_expired")
def purge_expired_task() -> int:
    with session_scope() as session:
        now = datetime.now(UTC)
        return purge_expired_bodies(session, now) + downsample_snapshots(session, now)


def queue_length() -> int | None:
    try:
        length: int = get_redis().llen("celery")  # type: ignore[assignment]
        return length
    except Exception:  # noqa: BLE001 - an unreachable Redis is itself an alert
        return None


def slow_requests(now: datetime) -> list[str] | None:
    from news_insight.observability import SLOW_KEY
    from news_insight.ops.checks import SLOW_WINDOW

    try:
        since = (now - SLOW_WINDOW).timestamp()
        raw = get_redis().zrangebyscore(SLOW_KEY, since, "+inf")
    except Exception:  # noqa: BLE001
        return None
    return [r.decode() if isinstance(r, bytes) else str(r) for r in raw]  # type: ignore[union-attr]


@celery_app.task(name="ops.check")
def ops_check_task() -> dict[str, Any]:
    from news_insight.ops.checks import run_checks
    from news_insight.ops.service import notify, sync_alerts

    now = datetime.now(UTC)
    with session_scope() as session:
        findings = run_checks(
            session, now=now, queue_length=queue_length(), slow_requests=slow_requests(now)
        )
        result = sync_alerts(session, findings, now=now)
        notify(get_settings(), result, now=now)
        return {
            "open": [a.key for a in result.open],
            "opened": [a.key for a in result.opened],
            "resolved": [a.key for a in result.resolved],
        }


@celery_app.task(name="technologies.refresh")
def technologies_refresh_task() -> dict[str, int]:
    from news_insight.technologies.service import recompute_all, refresh_labels

    with session_scope() as session:
        return {
            "cards_rekeyed": recompute_all(session),
            "labels": refresh_labels(session, now=datetime.now(UTC)),
        }


@celery_app.task(name="radar.warm")
def radar_warm_task() -> int:
    from news_insight.public.radar_cache import cache_client, warm

    client = cache_client()
    if client is None:
        return 0
    with session_scope() as session:
        return warm(session, now=datetime.now(UTC), client=client)
