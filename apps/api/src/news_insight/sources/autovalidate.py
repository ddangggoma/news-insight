"""Background ladder climb: moves unverified candidates to V3 so canary collection starts."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.models import Source, SourceValidationEvent
from news_insight.sources.service import climb

RETRY_AFTER = timedelta(hours=24)
SessionScope = Callable[[], AbstractContextManager[Session]]
BELOW_V3 = tuple(STAGE_ORDER[: STAGE_ORDER.index(ValidationStage.V3)])


@dataclass
class AutoValidateStats:
    checked: int = 0
    reached_v3: int = 0
    errors: int = 0
    failed: dict[str, int] = field(default_factory=dict)


def due_candidates(session: Session, *, now: datetime, limit: int) -> list[int]:
    """Candidates below V3 whose last failure (if any) is older than RETRY_AFTER."""
    last_failure = (
        select(
            SourceValidationEvent.source_id,
            func.max(SourceValidationEvent.created_at).label("failed_at"),
        )
        .where(SourceValidationEvent.outcome == ValidationOutcome.FAILED)
        .group_by(SourceValidationEvent.source_id)
        .subquery()
    )
    statement = (
        select(Source.id)
        .outerjoin(last_failure, last_failure.c.source_id == Source.id)
        .where(
            Source.status == SourceStatus.CANDIDATE,
            Source.validation_stage.in_(BELOW_V3),
            (last_failure.c.failed_at.is_(None)) | (last_failure.c.failed_at < now - RETRY_AFTER),
        )
        .order_by(last_failure.c.failed_at.asc().nulls_first(), Source.id)
        .limit(limit)
    )
    return list(session.scalars(statement))


def auto_validate(
    open_session: SessionScope,
    *,
    fetcher: SafeFetcher,
    now: datetime,
    limit: int = 100,
) -> AutoValidateStats:
    """One transaction per source so a broken source never rolls back the others."""
    with open_session() as session:
        source_ids = due_candidates(session, now=now, limit=limit)
    stats = AutoValidateStats()
    for source_id in source_ids:
        try:
            with open_session() as session:
                source = session.get(Source, source_id)
                if source is None:
                    continue
                events = climb(session, source, fetcher=fetcher, now=now)
                stats.checked += 1
                if source.validation_stage is ValidationStage.V3:
                    stats.reached_v3 += 1
                elif events and events[-1].outcome is ValidationOutcome.FAILED:
                    stage = events[-1].stage.value
                    stats.failed[stage] = stats.failed.get(stage, 0) + 1
        except Exception:  # noqa: BLE001 - one broken source must not stop the batch
            stats.errors += 1
    return stats
