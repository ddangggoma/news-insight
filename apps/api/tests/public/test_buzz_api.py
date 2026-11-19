from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.buzz.cluster import run
from news_insight.buzz.models import BuzzCluster
from tests.buzz.helpers import FixedHeat, news, post

pytestmark = pytest.mark.db
ARTICLE = "https://www.example-vendor.com/blog/launch"
OTHER = "https://example.org/another-story"


def test_buzz_lists_breaking_first_with_posts_and_news(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=50)
    post(db_session, "mastodon", 1, when=start, link=ARTICLE, title="This launch is wild")
    post(db_session, "bluesky", 2, when=start + timedelta(minutes=2), link=ARTICLE)
    post(db_session, "hn", 3, when=start + timedelta(minutes=4), link=ARTICLE)
    told = news(db_session, 1, when=now - timedelta(hours=5), url=OTHER, title="Old news story")
    for n, key in enumerate(("mastodon", "bluesky", "threads"), start=10):
        post(db_session, key, n, when=start, link=OTHER)
    post(db_session, "mastodon", 20, when=start, link="https://quiet.example/x")
    run(db_session, now=now - timedelta(minutes=30), heat=FixedHeat(0.6))
    breaking = db_session.scalars(select(BuzzCluster).where(BuzzCluster.breaking)).one()
    db_session.flush()

    response = public_client.get("/api/public/buzz", headers=public_headers)

    assert response.status_code == 200
    body = response.json()
    first, second = body["clusters"]
    assert first["breaking"] and not second["breaking"]
    assert first["title"] == "This launch is wild"  # the lead post until a summary is written
    assert not first["summarized"] and first["authors"] == 3
    assert first["platforms"] == ["bluesky", "fediverse", "hn"]
    assert first["id"] == breaking.id and first["sample"][0]["id"] == breaking.lead_item_id
    assert second["news"] == [
        {
            "id": told.id,
            "title": "Old news story",
            "url": OTHER,
            "source_name": "wire",
            "first_seen_at": second["news"][0]["first_seen_at"],
        }
    ]
    assert public_client.get("/api/public/buzz").status_code == 401
    assert public_client.get("/api/public/buzz?hours=0", headers=public_headers).status_code == 422
