from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.dead_letters import (
    DeadLetterError,
    dismiss,
    list_open,
    resume_transient,
    retry,
)
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


def paused_by(
    session: Session,
    reason: str,
    *,
    key: str = "example-news",
    last_success: timedelta | None = timedelta(hours=8),
    last_attempt: timedelta = timedelta(hours=7),
) -> Source:
    source = build_source(
        key=key,
        validation_stage=ValidationStage.V6,
        status=SourceStatus.PAUSED,
        paused_reason=reason,
    )
    session.add(source)
    session.flush()
    session.add(
        SourceRuntime(
            source_id=source.id,
            next_due_at=NOW + timedelta(hours=1),
            interval_seconds=7200,
            consecutive_failures=0,
            last_success_at=NOW - last_success if last_success is not None else None,
            last_attempt_at=NOW - last_attempt,
            lease_until=NOW,
        )
    )
    session.flush()
    return source


def test_a_transient_pause_resumes_after_its_cooldown(db_session: Session) -> None:
    source = paused_by(db_session, "repeated server_error: HTTP 503 from https://www.ebi.ac.uk/x")

    assert resume_transient(db_session, now=NOW) == [source]

    runtime = db_session.get(SourceRuntime, source.id)
    assert runtime is not None
    assert (source.status, source.paused_reason) == (SourceStatus.ACTIVE, None)
    assert (runtime.next_due_at, runtime.lease_until) == (NOW, None)


@pytest.mark.parametrize(
    "reason",
    [
        "repeated http_403: HTTP 403 from https://www.example.com/feed",
        "selector_drift: 12/17 feed entries lack id, link or title",
        "repeated blocked_mime: unexpected content type 'text/html'",
        "low DX relevance 4% (7d, n=26)",
        "timeout spotted by hand, checking the site",
    ],
)
def test_blocks_drift_and_manual_pauses_stay_paused(db_session: Session, reason: str) -> None:
    source = paused_by(db_session, reason)

    assert resume_transient(db_session, now=NOW) == []
    assert source.status is SourceStatus.PAUSED


def test_the_probe_waits_for_its_cooldown(db_session: Session) -> None:
    recent = paused_by(
        db_session, "repeated timeout: timed out", key="a", last_attempt=timedelta(hours=5)
    )
    # failing for three days: one probe a day
    slow = paused_by(
        db_session,
        "repeated timeout: timed out",
        key="b",
        last_success=timedelta(days=3),
        last_attempt=timedelta(hours=20),
    )
    due = paused_by(
        db_session,
        "repeated rate_limited: HTTP 429",
        key="c",
        last_success=timedelta(days=3),
        last_attempt=timedelta(hours=25),
    )

    assert resume_transient(db_session, now=NOW) == [due]
    assert recent.status is SourceStatus.PAUSED and slow.status is SourceStatus.PAUSED


def test_a_month_without_success_is_left_to_a_person(db_session: Session) -> None:
    stale = paused_by(
        db_session, "repeated server_error: HTTP 500", key="a", last_success=timedelta(days=31)
    )
    never = paused_by(db_session, "repeated server_error: HTTP 500", key="b", last_success=None)

    assert resume_transient(db_session, now=NOW) == []
    assert stale.status is SourceStatus.PAUSED and never.status is SourceStatus.PAUSED


def test_a_candidate_resumes_as_a_candidate(db_session: Session) -> None:
    source = paused_by(db_session, "repeated transport: peer closed connection")
    source.validation_stage = ValidationStage.V4

    resume_transient(db_session, now=NOW)

    assert source.status is SourceStatus.CANDIDATE
