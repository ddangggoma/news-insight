"""Pick sources whose next poll is due and lease them so they are dispatched once."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from news_insight.collect.models import SourceRuntime
from news_insight.collect.registry import SUPPORTED_METHODS
from news_insight.collect.service import COLLECTABLE_STAGES, ensure_runtime, is_collectable
from news_insight.sources.enums import SourceStatus
from news_insight.sources.models import Source

DISPATCH_LEASE = timedelta(minutes=15)


def _collectable_filters() -> tuple[Any, ...]:
    return (
        Source.access_method.in_(list(SUPPORTED_METHODS)),
        Source.validation_stage.in_(list(COLLECTABLE_STAGES)),
        Source.status.in_([SourceStatus.CANDIDATE, SourceStatus.ACTIVE]),
    )


def bootstrap_runtimes(session: Session, now: datetime) -> int:
    """Give newly collectable sources a runtime row that is due immediately."""
    missing = session.scalars(
        select(Source)
        .outerjoin(SourceRuntime, SourceRuntime.source_id == Source.id)
        .where(SourceRuntime.source_id.is_(None), *_collectable_filters())
    )
    created = 0
    for source in missing:
        if is_collectable(source):
            ensure_runtime(session, source, now)
            created += 1
    return created


def claim_due_sources(session: Session, now: datetime, *, limit: int = 50) -> list[int]:
    bootstrap_runtimes(session, now)
    statement = (
        select(SourceRuntime)
        .join(Source, Source.id == SourceRuntime.source_id)
        .where(
            SourceRuntime.next_due_at <= now,
            or_(SourceRuntime.lease_until.is_(None), SourceRuntime.lease_until < now),
            *_collectable_filters(),
        )
        .order_by(SourceRuntime.next_due_at)
        .limit(limit)
        .with_for_update(of=SourceRuntime, skip_locked=True)
    )
    runtimes = list(session.scalars(statement))
    for runtime in runtimes:
        runtime.lease_until = now + DISPATCH_LEASE
    session.flush()
    return [runtime.source_id for runtime in runtimes]
