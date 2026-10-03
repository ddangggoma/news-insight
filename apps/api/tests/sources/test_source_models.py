import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from news_insight.sources.enums import (
    STAGE_ORDER,
    SourceStatus,
    ValidationOutcome,
    ValidationStage,
)
from news_insight.sources.models import Source, SourceValidationEvent
from tests.factories import build_source, source_values

pytestmark = pytest.mark.db


def test_stage_order_is_unverified_then_v0_to_v6() -> None:
    assert [stage.value for stage in STAGE_ORDER] == [
        "unverified",
        "V0",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
    ]


def test_new_source_defaults_to_unverified_candidate(db_session: Session) -> None:
    source = Source(**source_values())
    db_session.add(source)
    db_session.flush()
    db_session.refresh(source)

    assert source.validation_stage is ValidationStage.UNVERIFIED
    assert source.status is SourceStatus.CANDIDATE
    assert source.config == {}
    assert source.created_at is not None


def test_source_key_is_unique(db_session: Session) -> None:
    db_session.add(build_source(key="dup"))
    db_session.flush()
    db_session.add(build_source(key="dup"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_enums_are_stored_as_plain_values(db_session: Session) -> None:
    db_session.add(build_source(key="plain"))
    db_session.flush()

    row = db_session.execute(
        text("SELECT track, region, validation_stage FROM sources WHERE key = 'plain'")
    ).one()

    assert tuple(row) == ("news", "global_en", "unverified")


def test_validation_events_are_ordered_by_insertion(db_session: Session) -> None:
    source = build_source(key="ordered")
    db_session.add(source)
    db_session.flush()
    for stage in (ValidationStage.V0, ValidationStage.V1):
        db_session.add(
            SourceValidationEvent(
                source=source, stage=stage, outcome=ValidationOutcome.PASSED, reasons=[], metrics={}
            )
        )
    db_session.flush()
    db_session.expire(source)

    assert [event.stage for event in source.validation_events] == [
        ValidationStage.V0,
        ValidationStage.V1,
    ]
