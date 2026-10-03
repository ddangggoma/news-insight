"""Dead-letter operations: inspect, dismiss, or send a source back for an immediate retry."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter
from news_insight.collect.service import ensure_runtime
from news_insight.sources.enums import SourceStatus
from news_insight.sources.models import Source


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
