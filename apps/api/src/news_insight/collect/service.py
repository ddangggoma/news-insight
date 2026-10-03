"""Collect one source: rate budget → collector → seen-ledger ingest → schedule / retry / DLQ."""

from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from news_insight.collect.context import collect_context
from news_insight.collect.contracts import Collector, CollectorError
from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.collect.registry import SUPPORTED_METHODS, collector_for
from news_insight.content.ingest import IngestStats, ingest_items
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.scheduling.policy import (
    MAX_RETRIES,
    initial_interval,
    is_idle,
    next_interval,
    retry_delay,
)
from news_insight.scheduling.redis_guards import RateLimiter
from news_insight.secrets import SecretError
from news_insight.sources.enums import STAGE_ORDER, AccessMethod, SourceStatus, ValidationStage
from news_insight.sources.ladder import is_schedulable, pause_source
from news_insight.sources.models import Source

CollectorFactory = Callable[[AccessMethod, SafeFetcher], Collector]
COLLECTABLE_STAGES = frozenset(STAGE_ORDER[STAGE_ORDER.index(ValidationStage.V3) :])
LOCAL_RATE_LIMIT_DELAY = timedelta(seconds=60)
MESSAGE_LIMIT = 2000
PAUSING_CODES = frozenset({"selector_drift", "config_error"})


def is_collectable(source: Source) -> bool:
    """V3+ candidates collect in canary mode; active sources must be V6."""
    if source.access_method not in SUPPORTED_METHODS:
        return False
    if source.validation_stage not in COLLECTABLE_STAGES:
        return False
    if source.status is SourceStatus.ACTIVE:
        return source.validation_stage is ValidationStage.V6
    return source.status is SourceStatus.CANDIDATE


def ensure_runtime(session: Session, source: Source, now: datetime) -> SourceRuntime:
    runtime = session.get(SourceRuntime, source.id)
    if runtime is None:
        runtime = SourceRuntime(
            source_id=source.id,
            next_due_at=now,
            interval_seconds=initial_interval(source.poll_class),
            consecutive_failures=0,
            consecutive_idle=0,
        )
        session.add(runtime)
        session.flush()
    return runtime


def collect_source(
    session: Session,
    source: Source,
    *,
    fetcher: SafeFetcher,
    limiter: RateLimiter,
    now: datetime,
    collector_factory: CollectorFactory = collector_for,
) -> FetchRun:
    runtime = ensure_runtime(session, source, now)
    run = FetchRun(
        source_id=source.id,
        started_at=now,
        attempt=runtime.consecutive_failures + 1,
        canary=not is_schedulable(source),
        outcome=FetchOutcome.SKIPPED,
    )
    session.add(run)
    session.flush()
    runtime.last_attempt_at = now
    runtime.lease_until = None

    if not is_collectable(source):
        return _finish(session, run, now, error_code="not_collectable")
    domain = urlsplit(source.endpoint_url).hostname or ""
    override = source.config.get("rate_per_minute")
    if not limiter.try_acquire(domain, per_minute=int(override) if override else None):
        runtime.next_due_at = now + LOCAL_RATE_LIMIT_DELAY
        return _finish(session, run, now, error_code="local_rate_limit")

    try:
        context = collect_context(
            source,
            now=now,
            etag=runtime.etag,
            last_modified=runtime.last_modified,
            last_success_at=runtime.last_success_at,
        )
    except (SecretError, ValueError) as exc:
        error = CollectorError("config_error", str(exc), retryable=False)
        return _handle_failure(session, source, runtime, run, error, now)
    try:
        result = collector_factory(source.access_method, fetcher).collect(context)
    except CollectorError as exc:
        return _handle_failure(session, source, runtime, run, exc, now)

    stats = (
        IngestStats()
        if result.not_modified
        else ingest_items(session, source, result.items, fetch_run=run, now=now, canary=run.canary)
    )
    run.outcome = FetchOutcome.NOT_MODIFIED if result.not_modified else FetchOutcome.SUCCESS
    run.http_status = result.status_code
    run.elapsed_ms = result.elapsed_ms
    run.items_seen = stats.seen
    run.items_new = stats.new
    run.items_updated = stats.updated
    run.items_unchanged = stats.unchanged
    run.items_incomplete = result.incomplete + stats.rejected
    run.duplicate_urls = stats.duplicate_urls

    idle = is_idle(
        not_modified=result.not_modified, new_items=stats.new, updated_items=stats.updated
    )
    runtime.interval_seconds = next_interval(
        source.poll_class, runtime.interval_seconds, idle=idle, new_items=stats.new
    )
    runtime.consecutive_failures = 0
    runtime.consecutive_idle = runtime.consecutive_idle + 1 if idle else 0
    runtime.etag = result.etag or runtime.etag
    runtime.last_modified = result.last_modified or runtime.last_modified
    runtime.last_success_at = now
    runtime.next_due_at = now + timedelta(seconds=runtime.interval_seconds)
    return _finish(session, run, now + timedelta(milliseconds=result.elapsed_ms))


def _handle_failure(
    session: Session,
    source: Source,
    runtime: SourceRuntime,
    run: FetchRun,
    exc: CollectorError,
    now: datetime,
) -> FetchRun:
    message = str(exc)[:MESSAGE_LIMIT]
    run.outcome = FetchOutcome.FAILED
    run.http_status = exc.status_code
    run.error_message = message
    pauses = exc.code in PAUSING_CODES or exc.code.startswith("blocked_")
    if exc.retryable and not pauses and run.attempt <= MAX_RETRIES:
        runtime.consecutive_failures = run.attempt
        runtime.next_due_at = now + timedelta(seconds=retry_delay(run.attempt))
        return _finish(session, run, now, error_code=exc.code)

    session.add(
        DeadLetter(
            source_id=source.id,
            fetch_run_id=run.id,
            error_code=exc.code,
            error_message=message,
            attempts=run.attempt,
        )
    )
    run.outcome = FetchOutcome.DEAD_LETTERED
    runtime.consecutive_failures = 0
    runtime.next_due_at = now + timedelta(seconds=runtime.interval_seconds)
    if pauses:
        pause_source(session, source, reason=f"{exc.code}: {message}"[:500])
    return _finish(session, run, now, error_code=exc.code)


def _finish(
    session: Session, run: FetchRun, finished_at: datetime, *, error_code: str | None = None
) -> FetchRun:
    run.finished_at = finished_at
    if error_code is not None:
        run.error_code = error_code
    session.flush()
    return run
