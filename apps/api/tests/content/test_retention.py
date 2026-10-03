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
