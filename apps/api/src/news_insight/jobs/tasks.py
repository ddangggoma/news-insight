"""Celery entry points. They wire sessions, locks and fetchers; logic lives in services."""

from datetime import UTC, datetime

from news_insight.collect.dispatch import claim_due_sources
from news_insight.collect.service import collect_source
from news_insight.config import get_settings
from news_insight.db import session_scope
from news_insight.jobs.celery_app import celery_app
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.redis_guards import DomainRateLimiter, SourceLock, get_redis
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
