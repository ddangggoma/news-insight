"""V0-V6 validation ladder: stages advance strictly in order and every attempt is audited."""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.models import Source, SourceValidationEvent


class LadderError(Exception):
    """A validation step was attempted out of order or on an ineligible source."""


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_reasons(
        cls, reasons: list[str], metrics: dict[str, Any] | None = None
    ) -> "CheckResult":
        return cls(passed=not reasons, reasons=reasons, metrics=metrics or {})


def next_stage(current: ValidationStage) -> ValidationStage | None:
    index = STAGE_ORDER.index(current)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None


def ensure_next_stage(source: Source, stage: ValidationStage) -> None:
    if source.status is SourceStatus.RETIRED:
        raise LadderError(f"{source.key}: retired sources cannot be validated")
    expected = next_stage(source.validation_stage)
    if expected is None:
        raise LadderError(f"{source.key}: already at {ValidationStage.V6.value}")
    if stage != expected:
        raise LadderError(f"{source.key}: next stage is {expected.value}, not {stage.value}")


def record_check(
    session: Session, source: Source, stage: ValidationStage, result: CheckResult
) -> SourceValidationEvent:
    ensure_next_stage(source, stage)
    event = SourceValidationEvent(
        source=source,
        stage=stage,
        outcome=ValidationOutcome.PASSED if result.passed else ValidationOutcome.FAILED,
        reasons=list(result.reasons),
        metrics=dict(result.metrics),
    )
    session.add(event)
    if result.passed:
        source.validation_stage = stage
        if stage is ValidationStage.V6 and source.status is SourceStatus.CANDIDATE:
            source.status = SourceStatus.ACTIVE
    session.flush()
    return event


def reset_validation(session: Session, source: Source, *, reason: str) -> SourceValidationEvent:
    source.validation_stage = ValidationStage.UNVERIFIED
    if source.status is not SourceStatus.RETIRED:
        source.status = SourceStatus.CANDIDATE
    source.paused_reason = None
    event = SourceValidationEvent(
        source=source,
        stage=ValidationStage.UNVERIFIED,
        outcome=ValidationOutcome.RESET,
        reasons=[reason],
        metrics={},
    )
    session.add(event)
    session.flush()
    return event


def pause_source(session: Session, source: Source, *, reason: str) -> None:
    if source.status is SourceStatus.RETIRED:
        raise LadderError(f"{source.key}: retired sources cannot be paused")
    source.status = SourceStatus.PAUSED
    source.paused_reason = reason
    session.flush()


def resume_source(session: Session, source: Source) -> None:
    if source.status is not SourceStatus.PAUSED:
        raise LadderError(f"{source.key}: only paused sources can resume")
    is_active = source.validation_stage is ValidationStage.V6
    source.status = SourceStatus.ACTIVE if is_active else SourceStatus.CANDIDATE
    source.paused_reason = None
    session.flush()


def is_schedulable(source: Source) -> bool:
    return source.status is SourceStatus.ACTIVE and source.validation_stage is ValidationStage.V6


def schedulable_sources(session: Session) -> list[Source]:
    statement = (
        select(Source)
        .where(Source.status == SourceStatus.ACTIVE, Source.validation_stage == ValidationStage.V6)
        .order_by(Source.key)
    )
    return list(session.scalars(statement))
