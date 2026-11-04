"""Dead-letter operations: inspect, dismiss, or send a source back for an immediate retry."""

import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter, SourceRuntime
from news_insight.collect.service import ensure_runtime
from news_insight.sources.enums import SourceStatus
from news_insight.sources.ladder import resume_source
from news_insight.sources.models import Source

log = logging.getLogger(__name__)


class DeadLetterError(Exception):
    """The dead letter cannot be resolved as requested."""


def list_open(session: Session, *, limit: int = 50) -> list[DeadLetter]:
    return list(
        session.scalars(
            select(DeadLetter)
            .where(DeadLetter.resolved_at.is_(None))
            .order_by(DeadLetter.id.desc())
            .limit(limit)
        )
    )


def _open_letter(session: Session, dead_letter_id: int) -> DeadLetter:
    letter = session.get(DeadLetter, dead_letter_id)
    if letter is None:
        raise DeadLetterError(f"dead letter #{dead_letter_id} does not exist")
    if letter.resolved_at is not None:
        raise DeadLetterError(f"dead letter #{dead_letter_id} is already resolved")
    return letter


def _resolve(session: Session, letter: DeadLetter, resolution: str, now: datetime) -> DeadLetter:
    letter.resolved_at = now
    letter.resolution = resolution
    session.flush()
    return letter


def dismiss(session: Session, dead_letter_id: int, *, now: datetime) -> DeadLetter:
    return _resolve(session, _open_letter(session, dead_letter_id), "dismissed", now)


def retry(session: Session, dead_letter_id: int, *, now: datetime) -> DeadLetter:
    letter = _open_letter(session, dead_letter_id)
    source = session.get(Source, letter.source_id)
    if source is None:
        raise DeadLetterError(f"source #{letter.source_id} no longer exists")
    if source.status is SourceStatus.PAUSED:
        raise DeadLetterError(f"{source.key} is paused ({source.paused_reason}); resume it first")
    runtime = ensure_runtime(session, source, now)
    runtime.next_due_at = now
    runtime.lease_until = None
    runtime.consecutive_failures = 0
    return _resolve(session, letter, "retried", now)


# Failures that say nothing about the source itself: its server, the network or a rate limit.
# A source paused by one of them is tried again after a cool-down (2026-10-29: a Europe PMC
# outage on 10-24 paused 80 searches and arXiv throttling 38 categories; none came back).
TRANSIENT_CODES = frozenset({"server_error", "timeout", "transport", "dns", "rate_limited"})
# a 403 or an HTML page in place of the feed is often a short bot wall or a maintenance page:
# 20 of 21 such pauses and 21 of 22 collected again on 2026-10-29. They wait a day each time.
SLOW_CODES = frozenset({"http_403", "blocked_mime"})
PAUSE_CODE = re.compile(r"(?:repeated )?([a-z0-9_]+): ")
PROBE_COOLDOWN = timedelta(hours=6)
SLOW_PROBE_COOLDOWN = timedelta(hours=24)  # once the source has been failing for two days
SLOW_AFTER = timedelta(days=2)
GIVE_UP_AFTER = timedelta(days=30)  # a month without a success is a person's call


def transient_pause_code(source: Source) -> str | None:
    """The failure code of an automatic pause that a later attempt may clear, else None."""
    if source.status is not SourceStatus.PAUSED or not source.paused_reason:
        return None
    match = PAUSE_CODE.match(source.paused_reason)
    code = match.group(1) if match else None
    return code if code in TRANSIENT_CODES | SLOW_CODES else None


def resume_transient(session: Session, *, now: datetime) -> list[Source]:
    """Resume the sources paused by a transient failure whose cool-down has passed.

    The open letter stays: if the failure is still there, the source pauses again after its
    retries ("repeated"), and its next probe waits another cool-down. A success closes the
    letter (collect/service.py). Sources without a success in GIVE_UP_AFTER stay paused."""
    rows = session.execute(
        select(Source, SourceRuntime)
        .join(SourceRuntime, SourceRuntime.source_id == Source.id)
        .where(Source.status == SourceStatus.PAUSED, Source.paused_reason.is_not(None))
        .order_by(Source.key)
    ).tuples()
    resumed: list[Source] = []
    for source, runtime in rows:
        code = transient_pause_code(source)
        if code is None or runtime.last_success_at is None:
            continue
        failing_for = now - runtime.last_success_at
        if failing_for > GIVE_UP_AFTER:
            continue
        slow = code in SLOW_CODES or failing_for > SLOW_AFTER
        cooldown = SLOW_PROBE_COOLDOWN if slow else PROBE_COOLDOWN
        last_attempt = runtime.last_attempt_at or runtime.last_success_at
        if now - last_attempt < cooldown:
            continue
        reason = source.paused_reason
        resume_source(session, source)
        runtime.next_due_at = now
        runtime.lease_until = None
        runtime.consecutive_failures = 0
        log.info(
            "source resumed after a transient pause", extra={"source": source.key, "reason": reason}
        )
        resumed.append(source)
    session.flush()
    return resumed
