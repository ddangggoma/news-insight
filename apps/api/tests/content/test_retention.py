from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.content.retention import purge_expired_bodies
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def test_purge_clears_only_expired_bodies(db_session: Session) -> None:
    source = build_source()
    db_session.add(source)
    db_session.flush()
    expiries = {
        "expired": NOW - timedelta(minutes=1),
        "fresh": NOW + timedelta(days=1),
        "kept": None,
    }
    for key, expires in expiries.items():
        db_session.add(
            Item(
                source_id=source.id,
                track=source.track,
                stable_id=key,
                url=f"https://www.example.com/{key}",
                canonical_url=f"https://www.example.com/{key}",
                title=key,
                body="full text",
                body_expires_at=expires,
                content_hash="0" * 64,
                first_seen_at=NOW,
                last_changed_at=NOW,
            )
        )
    db_session.flush()

    assert purge_expired_bodies(db_session, NOW) == 1
    bodies = {item.stable_id: item.body for item in db_session.scalars(select(Item))}
    assert bodies == {"expired": None, "fresh": "full text", "kept": "full text"}


def test_old_snapshots_thin_to_one_per_day_then_per_week(db_session: Session) -> None:
    from news_insight.content.models import ItemMetricSnapshot
    from news_insight.content.retention import downsample_snapshots

    source = build_source()
    db_session.add(source)
    db_session.flush()
    item = Item(
        source_id=source.id,
        track=source.track,
        stable_id="repo",
        url="https://www.example.com/repo",
        canonical_url="https://www.example.com/repo",
        title="repo",
        content_hash="0" * 64,
        first_seen_at=NOW - timedelta(days=400),
        last_changed_at=NOW,
    )
    db_session.add(item)
    db_session.flush()
    # KST noon and 18:00 (03:00, 09:00 UTC) on chosen days
    days = {
        "first": NOW - timedelta(days=400),  # the item's first snapshot: always kept
        "old_week_a": datetime(2026, 1, 5, 3, tzinfo=UTC),  # Mon, 2026-W02
        "old_week_b": datetime(2026, 1, 7, 3, tzinfo=UTC),  # Wed, same week: the week's last
        "month_a": NOW - timedelta(days=60, hours=6),
        "month_b": NOW - timedelta(days=60),  # same KST day, later: the day's last
        "recent_a": NOW - timedelta(days=2, hours=6),
        "recent_b": NOW - timedelta(days=2),  # under 30 days: untouched
    }
    for n, at in enumerate(days.values()):
        db_session.add(ItemMetricSnapshot(item_id=item.id, captured_at=at, metrics={"stars": n}))
    db_session.flush()

    assert downsample_snapshots(db_session, NOW) == 2
    kept = {
        at
        for (at,) in db_session.execute(
            select(ItemMetricSnapshot.captured_at).where(ItemMetricSnapshot.item_id == item.id)
        )
    }
    assert kept == {days[k] for k in ("first", "old_week_b", "month_b", "recent_a", "recent_b")}
    assert downsample_snapshots(db_session, NOW) == 0
