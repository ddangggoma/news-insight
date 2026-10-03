import pytest
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.ladder import (
    CheckResult,
    LadderError,
    is_schedulable,
    next_stage,
    pause_source,
    record_check,
    reset_validation,
    resume_source,
    schedulable_sources,
)
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db

PASS = CheckResult(passed=True)


def persisted(session: Session, **overrides: object) -> Source:
    source = build_source(**overrides)
    session.add(source)
    session.flush()
    return source


def climb_to(session: Session, source: Source, target: ValidationStage) -> None:
    for stage in STAGE_ORDER[1 : STAGE_ORDER.index(target) + 1]:
        record_check(session, source, stage, PASS)


def test_check_result_passes_only_without_reasons() -> None:
    assert CheckResult.from_reasons([]).passed is True
    failed = CheckResult.from_reasons(["terms_url is missing"], {"k": 1})
    assert failed.passed is False
    assert failed.reasons == ["terms_url is missing"]
    assert failed.metrics == {"k": 1}


def test_next_stage_walks_the_ladder() -> None:
    assert next_stage(ValidationStage.UNVERIFIED) is ValidationStage.V0
    assert next_stage(ValidationStage.V5) is ValidationStage.V6
    assert next_stage(ValidationStage.V6) is None


def test_passing_check_advances_stage_and_records_event(db_session: Session) -> None:
    source = persisted(db_session)

    event = record_check(db_session, source, ValidationStage.V0, PASS)

    assert source.validation_stage is ValidationStage.V0
    assert event.outcome is ValidationOutcome.PASSED
    assert event.source_id == source.id


def test_failing_check_keeps_stage_and_records_reasons(db_session: Session) -> None:
    source = persisted(db_session)

    event = record_check(
        db_session, source, ValidationStage.V0, CheckResult.from_reasons(["operator is missing"])
    )

    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert event.outcome is ValidationOutcome.FAILED
    assert event.reasons == ["operator is missing"]


def test_skipping_a_stage_is_rejected(db_session: Session) -> None:
    source = persisted(db_session)

    with pytest.raises(LadderError, match="next stage is V0"):
        record_check(db_session, source, ValidationStage.V2, PASS)


def test_reaching_v6_activates_candidate(db_session: Session) -> None:
    source = persisted(db_session)

    climb_to(db_session, source, ValidationStage.V6)

    assert source.status is SourceStatus.ACTIVE
    assert is_schedulable(source) is True
    assert schedulable_sources(db_session) == [source]
    with pytest.raises(LadderError, match="already at V6"):
        record_check(db_session, source, ValidationStage.V6, PASS)


def test_paused_source_is_not_schedulable_until_resumed(db_session: Session) -> None:
    source = persisted(db_session)
    climb_to(db_session, source, ValidationStage.V6)

    pause_source(db_session, source, reason="selector drift")

    assert source.status is SourceStatus.PAUSED
    assert source.paused_reason == "selector drift"
    assert schedulable_sources(db_session) == []

    resume_source(db_session, source)

    assert source.status is SourceStatus.ACTIVE
    assert source.paused_reason is None


def test_resume_of_unvalidated_source_returns_to_candidate(db_session: Session) -> None:
    source = persisted(db_session)
    pause_source(db_session, source, reason="operator hold")

    resume_source(db_session, source)

    assert source.status is SourceStatus.CANDIDATE


def test_reset_returns_to_unverified_candidate(db_session: Session) -> None:
    source = persisted(db_session)
    climb_to(db_session, source, ValidationStage.V6)

    event = reset_validation(db_session, source, reason="endpoint changed")

    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert source.status is SourceStatus.CANDIDATE
    assert event.outcome is ValidationOutcome.RESET
    assert event.reasons == ["endpoint changed"]


def test_retired_source_cannot_be_validated(db_session: Session) -> None:
    source = persisted(db_session, status=SourceStatus.RETIRED)

    with pytest.raises(LadderError, match="retired"):
        record_check(db_session, source, ValidationStage.V0, PASS)
