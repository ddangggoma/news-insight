from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)

pytestmark = pytest.mark.db
DAY = date(2026, 11, 3)


def _freeze(session: Session, day: date = DAY) -> SpotlightFreeze:
    freeze = SpotlightFreeze(
        spotlight_date=day,
        frozen_at=datetime(2026, 11, 2, 20, 0, tzinfo=UTC),
        candidates={"news": [{"key": "story:1", "item_ids": [1, 2]}]},
    )
    session.add(freeze)
    session.flush()
    return freeze


def _spotlight(session: Session, freeze: SpotlightFreeze, day: date = DAY) -> Spotlight:
    spotlight = Spotlight(
        spotlight_date=day,
        status=SpotlightStatus.PUBLISHED,
        model="claude-opus",
        headline="오늘의 주목",
        benchmark_note="",
        freeze_id=freeze.id,
        generated_at=datetime(2026, 11, 2, 21, 0, tzinfo=UTC),
    )
    session.add(spotlight)
    session.flush()
    return spotlight


def _entry(spotlight_id: int, rank: int, section: str = "news") -> SpotlightEntry:
    return SpotlightEntry(
        spotlight_id=spotlight_id,
        section=section,
        rank=rank,
        stat_rank=rank,
        key=f"story:{rank}",
        item_ids=[rank],
        title_ko="제목",
        summary="요약",
        why_hot="이유",
    )


def test_round_trip_defaults(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    entry = _entry(spotlight.id, 1)
    db_session.add(entry)
    db_session.flush()
    db_session.refresh(entry)
    assert entry.fallback is False
    assert entry.metrics == {}
    assert entry.product_name is None and entry.rank_note is None
    assert spotlight.cost_usd is None and spotlight.error is None


def test_entry_unique_rank_per_section(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    db_session.add_all([_entry(spotlight.id, 1), _entry(spotlight.id, 1)])
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_rank_allowed_in_other_section(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    db_session.add_all([_entry(spotlight.id, 1), _entry(spotlight.id, 1, section="oss")])
    db_session.flush()


def test_spotlight_date_unique(db_session: Session) -> None:
    freeze = _freeze(db_session)
    _spotlight(db_session, freeze)
    with pytest.raises(IntegrityError):
        _spotlight(db_session, freeze)


def test_freeze_date_unique(db_session: Session) -> None:
    _freeze(db_session)
    with pytest.raises(IntegrityError):
        _freeze(db_session)


def test_entries_cascade_with_spotlight(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    entry = _entry(spotlight.id, 1)
    db_session.add(entry)
    db_session.flush()
    db_session.delete(spotlight)
    db_session.flush()
    remaining = db_session.scalar(
        select(func.count()).select_from(SpotlightEntry).where(SpotlightEntry.id == entry.id)
    )
    assert remaining == 0
