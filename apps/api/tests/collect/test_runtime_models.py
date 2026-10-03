from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def persisted_source(session: Session) -> Source:
    source = build_source()
    session.add(source)
    session.flush()
    return source


def test_runtime_defaults(db_session: Session) -> None:
    source = persisted_source(db_session)
    runtime = SourceRuntime(source_id=source.id, next_due_at=NOW, interval_seconds=900)
    db_session.add(runtime)
    db_session.flush()
    db_session.refresh(runtime)

    assert (runtime.consecutive_failures, runtime.consecutive_idle) == (0, 0)
    assert (runtime.etag, runtime.lease_until) == (None, None)


def test_fetch_run_stores_plain_outcome_value(db_session: Session) -> None:
    source = persisted_source(db_session)
    run = FetchRun(source_id=source.id, started_at=NOW, outcome=FetchOutcome.NOT_MODIFIED)
    db_session.add(run)
    db_session.flush()

    row = db_session.execute(
        text("SELECT outcome, attempt, canary, items_new FROM fetch_runs WHERE id = :id"),
        {"id": run.id},
    ).one()

    assert tuple(row) == ("not_modified", 1, False, 0)


def test_dead_letters_start_unresolved(db_session: Session) -> None:
    source = persisted_source(db_session)
    letter = DeadLetter(
        source_id=source.id, error_code="timeout", error_message="timed out", attempts=4
    )
    db_session.add(letter)
    db_session.flush()
    db_session.refresh(letter)

    assert letter.resolved_at is None
    assert letter.created_at is not None


def test_deleting_a_source_cascades_runtime_state(db_session: Session) -> None:
    source = persisted_source(db_session)
    run = FetchRun(source_id=source.id, started_at=NOW, outcome=FetchOutcome.FAILED)
    db_session.add_all(
        [SourceRuntime(source_id=source.id, next_due_at=NOW, interval_seconds=900), run]
    )
    db_session.flush()
    db_session.add(
        DeadLetter(
            source_id=source.id, fetch_run_id=run.id, error_code="x", error_message="x", attempts=1
        )
    )
    db_session.flush()

    db_session.execute(delete(Source).where(Source.id == source.id))

    for model in (SourceRuntime, FetchRun, DeadLetter):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0
