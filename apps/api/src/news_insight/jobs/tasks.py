"""Celery entry points. They wire sessions, locks and fetchers; logic lives in services."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from news_insight.collect.dispatch import claim_due_sources
from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.content.retention import purge_expired_bodies
from news_insight.db import session_scope
from news_insight.jobs.celery_app import celery_app
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.redis_guards import DomainRateLimiter, SourceLock, get_redis
from news_insight.sources.autovalidate import auto_validate
from news_insight.sources.canary import run_canaries
from news_insight.sources.models import Source


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
            session_scope, fetcher=fetcher, now=datetime.now(UTC), limit=AUTO_VALIDATE_BATCH
        )
    return asdict(stats)


@celery_app.task(name="content.purge_expired")
def purge_expired_task() -> int:
    with session_scope() as session:
        return purge_expired_bodies(session, datetime.now(UTC))
