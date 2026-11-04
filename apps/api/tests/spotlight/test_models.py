import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightGroup,
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
    assert (entry.group, entry.tags, entry.signals, entry.field) == ("now", [], [], None)


def test_entry_unique_rank_per_section(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    db_session.add_all([_entry(spotlight.id, 1), _entry(spotlight.id, 1)])
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_rank_allowed_in_other_section(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    db_session.add_all([_entry(spotlight.id, 1), _entry(spotlight.id, 1, section="oss")])
    db_session.flush()


def test_same_rank_allowed_in_the_other_group(db_session: Session) -> None:
    spotlight = _spotlight(db_session, _freeze(db_session))
    later = _entry(spotlight.id, 1)
    later.key, later.group = "story:9", SpotlightGroup.SUSTAINED
    db_session.add_all([_entry(spotlight.id, 1), later])
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


def _migration() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations/versions/0047_spotlight_groups.py"
    spec = importlib.util.spec_from_file_location("migration_0047", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(session: Session) -> set[str]:
    return set(
        session.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'spotlight_entries'"
            )
        ).scalars()
    )


def test_migration_0047_down_and_up(db_session: Session) -> None:
    """Inside the test's transaction (DDL is transactional): down drops the sustained rows
    and the new columns, up brings rows back as group "now" with no tags, signals or field."""
    spotlight = _spotlight(db_session, _freeze(db_session))
    db_session.add_all(
        [
            _entry(spotlight.id, 1),
            SpotlightEntry(
                spotlight_id=spotlight.id,
                section="news",
                rank=1,
                stat_rank=1,
                key="story:9",
                item_ids=[9],
                title_ko="지속",
                summary="",
                why_hot="",
                metrics={},
                group=SpotlightGroup.SUSTAINED,
                tags=["장기 화제"],
                signals=["7일 중 4일"],
                field="ai",
            ),
        ]
    )
    db_session.flush()
    module = _migration()
    with Operations.context(MigrationContext.configure(db_session.connection())):
        module.downgrade()
        assert {"group", "tags", "signals", "field"}.isdisjoint(_columns(db_session))
        assert db_session.execute(text("SELECT key FROM spotlight_entries")).scalars().all() == [
            "story:1"
        ]
        module.upgrade()
    assert {"group", "tags", "signals", "field"} <= _columns(db_session)
    row = db_session.execute(
        text('SELECT "group", tags, signals, field FROM spotlight_entries')
    ).one()
    assert tuple(row) == ("now", [], [], None)
