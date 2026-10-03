"""Orchestrates ladder checks: picks the checker for a stage and records the outcome."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.auto_policy import AUTO_STORAGE_RIGHT, check_auto_policy
from news_insight.sources.checks import (
    check_identity,
    check_network,
    check_parser,
    check_policy,
)
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import (
    CheckResult,
    LadderError,
    ensure_next_stage,
    next_stage,
    record_check,
)
from news_insight.sources.models import Source, SourceValidationEvent
from news_insight.sources.portfolio import active_portfolio, check_quota

AUTOMATED_STAGES = frozenset(
    {
        ValidationStage.V0,
        ValidationStage.V1,
        ValidationStage.V2,
        ValidationStage.V3,
        ValidationStage.V6,
    }
)


class SourceNotFound(LookupError):
    """No source with the requested key."""


class StageNotAutomated(LadderError):
    """The stage needs collection metrics that Phase 2 runners will provide."""


def get_source(session: Session, key: str) -> Source:
    source = session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if source is None:
        raise SourceNotFound(f"unknown source '{key}'")
    return source


def _evaluate(
    session: Session, source: Source, stage: ValidationStage, fetcher: SafeFetcher, now: datetime
) -> CheckResult:
    if stage is ValidationStage.V0:
        return check_identity(source)
    if stage is ValidationStage.V1:
        if source.terms_url:
            return check_policy(source)
        result = check_auto_policy(source, fetcher)
        if result.passed and source.storage_right is None:
            source.storage_right = AUTO_STORAGE_RIGHT
        return result
    if stage is ValidationStage.V2:
        return check_network(source, fetcher)
    if stage is ValidationStage.V3:
        return check_parser(source, fetcher, now=now)
    if stage is ValidationStage.V6:
        return check_quota(active_portfolio(session), track=source.track, region=source.region)
    raise StageNotAutomated(
        f"{stage.value} is judged from collection metrics "
        "(V4: `news-insight sources canary`; V5: Phase 5)"
    )


def run_check(
    session: Session,
    source: Source,
    stage: ValidationStage,
    *,
    fetcher: SafeFetcher,
    now: datetime,
) -> SourceValidationEvent:
    ensure_next_stage(source, stage)
    if stage not in AUTOMATED_STAGES:
        raise StageNotAutomated(
            f"{stage.value} is judged from collection metrics "
            "(V4: `news-insight sources canary`; V5: Phase 5)"
        )
    result = _evaluate(session, source, stage, fetcher, now)
    return record_check(session, source, stage, result)


def climb(
    session: Session,
    source: Source,
    *,
    fetcher: SafeFetcher,
    now: datetime,
    until: ValidationStage = ValidationStage.V3,
) -> list[SourceValidationEvent]:
    events: list[SourceValidationEvent] = []
    while (stage := next_stage(source.validation_stage)) is not None and STAGE_ORDER.index(
        stage
    ) <= STAGE_ORDER.index(until):
        event = run_check(session, source, stage, fetcher=fetcher, now=now)
        events.append(event)
        if event.outcome is ValidationOutcome.FAILED:
            break
    return events


def stage_counts(session: Session) -> dict[ValidationStage, int]:
    rows = session.execute(
        select(Source.validation_stage, func.count()).group_by(Source.validation_stage)
    )
    return {stage: count for stage, count in rows}


def probe_source(
    source: Source, *, fetcher: SafeFetcher, now: datetime
) -> list[tuple[ValidationStage, CheckResult]]:
    """Dry-run V0-V3 without touching the ladder or the database."""
    return [
        (ValidationStage.V0, check_identity(source)),
        (ValidationStage.V1, check_policy(source)),
        (ValidationStage.V2, check_network(source, fetcher)),
        (ValidationStage.V3, check_parser(source, fetcher, now=now)),
    ]
