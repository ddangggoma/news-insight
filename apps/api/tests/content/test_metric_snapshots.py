from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import ItemMetricSnapshot
from news_insight.content.trends import metric_movers
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def repo(name: str, stars: int) -> RawItem:
    return RawItem(
        stable_id=name, url=f"https://github.com/{name}", title=name, metrics={"stars": stars}
    )


def source(session: Session, **overrides: Any) -> Source:
    created = build_source(**{"key": "oss", "track": Track.OSS, **overrides})
    session.add(created)
    session.flush()
    return created


def ingest(session: Session, src: Source, items: list[RawItem], at: datetime) -> int:
    return ingest_items(session, src, items, fetch_run=None, now=at, canary=True).snapshots


def snapshots(session: Session) -> list[dict[str, int]]:
    rows = session.scalars(select(ItemMetricSnapshot).order_by(ItemMetricSnapshot.id))
    return [row.metrics for row in rows]


def test_first_sighting_records_a_snapshot(db_session: Session) -> None:
    assert ingest(db_session, source(db_session), [repo("a/b", 10)], NOW) == 1
    assert snapshots(db_session) == [{"stars": 10}]


def test_changes_within_an_hour_are_not_recorded(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("a/b", 10)], NOW)

    assert ingest(db_session, src, [repo("a/b", 12)], NOW + timedelta(minutes=30)) == 0


def test_changes_after_an_hour_are_recorded(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("a/b", 10)], NOW)

    assert ingest(db_session, src, [repo("a/b", 12)], NOW + timedelta(hours=2)) == 1
    assert snapshots(db_session) == [{"stars": 10}, {"stars": 12}]


def test_unchanged_values_are_not_recorded(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("a/b", 10)], NOW)

    assert ingest(db_session, src, [repo("a/b", 10)], NOW + timedelta(hours=2)) == 0


def test_movers_rank_by_delta_over_the_window(db_session: Session) -> None:
    src = source(db_session)
    ingest(db_session, src, [repo("fast/one", 100), repo("slow/two", 100)], NOW - timedelta(days=2))
    ingest(
        db_session,
        src,
        [repo("fast/one", 150), repo("slow/two", 110)],
        NOW - timedelta(days=1, hours=1),
    )
    ingest(db_session, src, [repo("fast/one", 400), repo("slow/two", 120)], NOW)

    movers = metric_movers(db_session, metric="stars", window=timedelta(days=1), now=NOW)

    assert [(m.item.title, m.baseline, m.current, m.delta) for m in movers] == [
        ("fast/one", 150, 400, 250),
        ("slow/two", 110, 120, 10),
    ]


def test_movers_need_two_points_and_respect_the_track(db_session: Session) -> None:
    oss = source(db_session)
    news = source(db_session, key="news", track=Track.NEWS)
    ingest(db_session, oss, [repo("only/once", 5)], NOW)
    ingest(db_session, news, [repo("n/1", 1)], NOW - timedelta(days=2))
    ingest(db_session, news, [repo("n/1", 9)], NOW)

    assert (
        metric_movers(
            db_session, metric="stars", window=timedelta(days=1), now=NOW, track=Track.OSS
        )
        == []
    )
