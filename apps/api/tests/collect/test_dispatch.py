from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.dispatch import DISPATCH_LEASE, bootstrap_runtimes, claim_due_sources
from news_insight.collect.models import SourceRuntime
from news_insight.sources.enums import AccessMethod, SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def add(session: Session, key: str, **overrides: Any) -> Source:
    values: dict[str, Any] = {"key": key, "validation_stage": ValidationStage.V3, **overrides}
    source = build_source(**values)
    session.add(source)
    session.flush()
    return source


def schedule(
    session: Session, source: Source, *, due: datetime, lease: datetime | None = None
) -> None:
    session.add(
        SourceRuntime(source_id=source.id, next_due_at=due, interval_seconds=900, lease_until=lease)
    )
    session.flush()


def test_bootstrap_creates_runtimes_for_collectable_sources_only(db_session: Session) -> None:
    feed = add(db_session, "feed")
    active = add(
        db_session, "active", validation_stage=ValidationStage.V6, status=SourceStatus.ACTIVE
    )
    add(db_session, "early", validation_stage=ValidationStage.V2)
    add(db_session, "github", access_method=AccessMethod.GITHUB)
    add(db_session, "paused", status=SourceStatus.PAUSED)

    created = bootstrap_runtimes(db_session, NOW)

    ids = set(db_session.scalars(select(SourceRuntime.source_id)))
    assert created == 2
    assert ids == {feed.id, active.id}


def test_claims_due_sources_and_sets_a_lease(db_session: Session) -> None:
    source = add(db_session, "due")
    schedule(db_session, source, due=NOW - timedelta(minutes=1))

    assert claim_due_sources(db_session, NOW) == [source.id]
    runtime = db_session.get(SourceRuntime, source.id)
    assert runtime is not None and runtime.lease_until == NOW + DISPATCH_LEASE


def test_skips_future_and_leased_sources(db_session: Session) -> None:
    schedule(db_session, add(db_session, "future"), due=NOW + timedelta(minutes=5))
    schedule(
        db_session,
        add(db_session, "leased"),
        due=NOW - timedelta(minutes=5),
        lease=NOW + timedelta(minutes=5),
    )

    assert claim_due_sources(db_session, NOW) == []


def test_expired_leases_are_reclaimed(db_session: Session) -> None:
    source = add(db_session, "stale")
    schedule(db_session, source, due=NOW - timedelta(minutes=30), lease=NOW - timedelta(minutes=1))

    assert claim_due_sources(db_session, NOW) == [source.id]


def test_claims_respect_the_limit_in_due_order(db_session: Session) -> None:
    sources = [add(db_session, f"s{n}") for n in range(3)]
    for offset, source in enumerate(sources):
        schedule(db_session, source, due=NOW - timedelta(minutes=10 - offset))

    assert claim_due_sources(db_session, NOW, limit=2) == [sources[0].id, sources[1].id]
