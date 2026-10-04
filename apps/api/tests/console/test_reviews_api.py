from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import Track
from tests.factories import build_source

pytestmark = pytest.mark.db


def seed(db_session: Session) -> list[int]:
    now = datetime.now(UTC)
    news = build_source(key="news", name="The Verge")
    oss = build_source(key="oss", name="GitHub", track=Track.OSS, category="oss_trend")
    db_session.add_all([news, oss])
    db_session.flush()
    for source, prefix in ((news, "n"), (oss, "o")):
        ingest_items(
            db_session,
            source,
            [
                RawItem(
                    stable_id=f"{prefix}{i}",
                    url=f"https://www.example.com/{prefix}{i}",
                    title=f"{prefix} {i}",
                )
                for i in range(5)
            ],
            fetch_run=None,
            now=now,
            canary=True,
        )
    items = list(db_session.scalars(select(Item).order_by(Item.id)))
    db_session.add_all(
        ItemCard(
            item_id=item.id,
            status=CardStatus.READY,
            title_ko=f"카드 {item.title}",
            summary_ko=[],
            keywords=[],
            engine="agy",
            model="m",
            input_hash=item.content_hash,
            attempts=0,
            generated_at=now,
        )
        for item in items
    )
    db_session.flush()
    return [item.id for item in items]


def test_sample_is_reproducible_per_seed_and_filterable(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    first = console_client.get("/api/admin/reviews/sample?seed=abc&size=6", headers=headers).json()
    again = console_client.get("/api/admin/reviews/sample?seed=abc&size=6", headers=headers).json()
    other = console_client.get("/api/admin/reviews/sample?seed=xyz&size=6", headers=headers).json()
    oss = console_client.get("/api/admin/reviews/sample?seed=abc&track=oss", headers=headers).json()

    ids = [view["item"]["id"] for view in first["items"]]
    assert len(ids) == 6 and ids == [view["item"]["id"] for view in again["items"]]
    assert ids != [view["item"]["id"] for view in other["items"]]
    assert {view["item"]["track"] for view in oss["items"]} == {"oss"}
    assert first["items"][0]["card"]["title_ko"].startswith("카드")


def test_reviews_upsert_and_feed_stats_and_csv(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    ids = seed(db_session)
    verdicts = ["relevant", "irrelevant", "relevant", "unsure"]
    for item_id, verdict in zip(ids[:4], verdicts, strict=True):
        response = console_client.post(
            "/api/admin/reviews",
            headers=headers,
            json={"item_id": item_id, "verdict": verdict, "seed": "abc"},
        )
        assert response.status_code == 200
    console_client.post(
        "/api/admin/reviews",
        headers=headers,
        json={"item_id": ids[1], "verdict": "relevant", "note": "재검토"},
    )

    stats = console_client.get("/api/admin/reviews/stats", headers=headers).json()
    sample = console_client.get(
        "/api/admin/reviews/sample?seed=abc&size=10", headers=headers
    ).json()
    csv = console_client.get("/api/admin/reviews/export.csv", headers=headers)
    missing = console_client.post(
        "/api/admin/reviews", headers=headers, json={"item_id": 999999, "verdict": "relevant"}
    )

    assert stats["overall"] == {
        "key": "전체",
        "total": 4,
        "relevant": 3,
        "irrelevant": 0,
        "unsure": 1,
    }
    assert sample["reviewed"] == 4
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.count("\n") == 5 and "재검토" in csv.text
    assert missing.status_code == 404
