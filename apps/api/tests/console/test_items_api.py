from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.sources.enums import Track
from tests.factories import build_source

pytestmark = pytest.mark.db


def seed(db_session: Session) -> None:
    now = datetime.now(UTC)
    news = build_source(key="news")
    oss = build_source(key="oss", track=Track.OSS)
    db_session.add_all([news, oss])
    db_session.flush()
    ingest_items(
        db_session,
        news,
        [
            RawItem(stable_id="n1", url="https://www.example.com/n1", title="Galaxy S30 출시"),
            RawItem(stable_id="n2", url="https://www.example.com/n2", title="OLED 패널 단가"),
        ],
        fetch_run=None,
        now=now - timedelta(days=10),
        canary=True,
    )
    for hours, stars in ((48, 100), (0, 250)):
        ingest_items(
            db_session,
            oss,
            [
                RawItem(
                    stable_id="r",
                    url="https://github.com/a/b",
                    title="a/b",
                    metrics={"stars": stars},
                )
            ],
            fetch_run=None,
            now=now - timedelta(hours=hours),
            canary=True,
        )


def test_items_support_search_track_and_recency(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    everything = console_client.get("/api/admin/items", headers=headers).json()
    searched = console_client.get("/api/admin/items?q=galaxy", headers=headers).json()
    recent_oss = console_client.get("/api/admin/items?track=oss&days=3", headers=headers).json()

    assert everything["total"] == 3
    assert [item["title"] for item in searched["items"]] == ["Galaxy S30 출시"]
    assert [item["metrics"] for item in recent_oss["items"]] == [{"stars": 250}]


def test_item_detail_and_movers(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)
    item_id = console_client.get("/api/admin/items?track=oss", headers=headers).json()["items"][0][
        "id"
    ]

    detail = console_client.get(f"/api/admin/items/{item_id}", headers=headers).json()
    movers = console_client.get(
        "/api/admin/trends/movers?metric=stars&days=1", headers=headers
    ).json()

    assert [point["metrics"]["stars"] for point in detail["metric_history"]] == [100, 250]
    assert [revision["revision"] for revision in detail["revisions"]] == [1]
    assert [(mover["item"]["title"], mover["delta"]) for mover in movers] == [("a/b", 150)]
    assert console_client.get("/api/admin/items/999999", headers=headers).status_code == 404
