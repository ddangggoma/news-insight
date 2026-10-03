from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.dead_letters import DeadLetterError, dismiss, list_open, retry
from news_insight.collect.models import DeadLetter, SourceRuntime
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def source_with_letter(session: Session, **overrides: Any) -> tuple[Source, DeadLetter]:
    source = build_source(**{"validation_stage": ValidationStage.V3, **overrides})
    session.add(source)
    session.flush()
    session.add(
        SourceRuntime(
            source_id=source.id,
            next_due_at=NOW + timedelta(hours=1),
            interval_seconds=900,
            consecutive_failures=2,
        )
    )
    letter = DeadLetter(source_id=source.id, error_code="timeout", error_message="t", attempts=4)
    session.add(letter)
    session.flush()
    return source, letter


def test_list_open_returns_unresolved_newest_first(db_session: Session) -> None:
    _, first = source_with_letter(db_session, key="a")
    _, second = source_with_letter(db_session, key="b")
    dismiss(db_session, first.id, now=NOW)

    assert list_open(db_session) == [second]


def test_dismiss_records_the_resolution(db_session: Session) -> None:
    _, letter = source_with_letter(db_session)

    dismiss(db_session, letter.id, now=NOW)

    assert (letter.resolved_at, letter.resolution) == (NOW, "dismissed")


def test_retry_makes_the_source_due_now(db_session: Session) -> None:
    source, letter = source_with_letter(db_session)

    retry(db_session, letter.id, now=NOW)

    runtime = db_session.get(SourceRuntime, source.id)
    assert runtime is not None
    assert (runtime.next_due_at, runtime.consecutive_failures, runtime.lease_until) == (
        NOW,
        0,
        None,
    )
    assert letter.resolution == "retried"


def test_retry_refuses_paused_sources(db_session: Session) -> None:
    _, letter = source_with_letter(
        db_session, status=SourceStatus.PAUSED, paused_reason="selector_drift: x"
    )

    with pytest.raises(DeadLetterError, match="resume it first"):
        retry(db_session, letter.id, now=NOW)


def test_resolved_letters_cannot_be_resolved_again(db_session: Session) -> None:
    _, letter = source_with_letter(db_session)
    dismiss(db_session, letter.id, now=NOW)

    with pytest.raises(DeadLetterError, match="already resolved"):
        dismiss(db_session, letter.id, now=NOW)
