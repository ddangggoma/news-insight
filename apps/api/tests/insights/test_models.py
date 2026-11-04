"""domain_insights (migration 0050): one row per date and kind, and the migration's down/up."""

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from news_insight.insights.models import DomainInsightRecord, InsightKind, InsightStatus

pytestmark = pytest.mark.db
DAY = date(2026, 11, 4)


def _row(kind: InsightKind = InsightKind.RESEARCH) -> DomainInsightRecord:
    return DomainInsightRecord(
        insight_date=DAY,
        kind=kind,
        status=InsightStatus.PUBLISHED,
        model="claude-opus-5-5",
        cost_usd=1.2345,
        payload={"overview": []},
        generated_at=datetime(2026, 11, 3, 20, tzinfo=UTC),
    )


def _migration() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "migrations/versions/0050_domain_insights.py"
    spec = importlib.util.spec_from_file_location("migration_0050", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_one_row_per_date_and_kind(db_session: Session) -> None:
    db_session.add_all([_row(), _row(InsightKind.PATENT)])
    db_session.flush()
    stored = db_session.get(DomainInsightRecord, _row_id(db_session))
    assert stored is not None and stored.cost_usd == 1.2345
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_row())
        db_session.flush()


def _row_id(session: Session) -> int:
    return int(session.execute(text("SELECT min(id) FROM domain_insights")).scalar_one())


def test_migration_downgrade_and_upgrade(db_session: Session) -> None:
    module = _migration()
    assert module.revision == "0050" and module.down_revision == "0049"
    with Operations.context(MigrationContext.configure(db_session.connection())):
        module.downgrade()
        assert "domain_insights" not in inspect(db_session.connection()).get_table_names()
        module.upgrade()
    assert "domain_insights" in inspect(db_session.connection()).get_table_names()
    db_session.add(_row())
    db_session.flush()
