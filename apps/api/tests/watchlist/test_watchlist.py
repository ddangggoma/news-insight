from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
from news_insight.watchlist import service as watchlist
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 6, 3, tzinfo=UTC)
_serial = iter(range(10_000))


def card(
    db_session: Session,
    *,
    keywords: list[str] = (),  # type: ignore[assignment]
    companies: list[str] = (),  # type: ignore[assignment]
    themes: list[str] = (),  # type: ignore[assignment]
    relevance: int = 50,
    seen: datetime = NOW - timedelta(hours=10),
) -> int:
    from news_insight.sources.models import Source

    source = db_session.scalars(select(Source).where(Source.key == "example-news")).first()
    if source is None:
        source = build_source()
        db_session.add(source)
        db_session.flush()
    url = f"https://www.example.com/w{next(_serial)}"
    ingest_items(
        db_session,
        source,
        [RawItem(stable_id=url, url=url, title="t")],
        fetch_run=None,
        now=seen,
        canary=True,
    )
    item = db_session.scalars(select(Item).where(Item.url == url)).one()
    db_session.add(
        ItemCard(
            item_id=item.id,
            status=CardStatus.READY,
            title_ko="카드",
            summary_ko=[],
            keywords=list(keywords),
            companies=list(companies),
            themes=list(themes),
            input_hash=item.content_hash,
            generated_at=seen,
            scope="dx",
            relevance=relevance,
            taxonomy_revision=TAXONOMY_REVISION,
        )
    )
    db_session.flush()
    return item.id


def test_add_validates_and_normalises(db_session: Session) -> None:
    company = watchlist.add(db_session, kind="company", value="qualcomm")
    theme = watchlist.add(db_session, kind="theme", value="ai__on_device_ai")
    keyword = watchlist.add(db_session, kind="keyword", value="AI 에이전트")

    assert (company.label, theme.label) == ("퀄컴", "온디바이스 AI·디바이스 AI 경험")
    assert keyword.key == "ai에이전트" and keyword.label == "AI 에이전트"
    assert (
        watchlist.add(db_session, kind="company", value="qualcomm").id == company.id
    )  # no duplicate
    for kind, value in (
        ("company", "nope"),
        ("theme", "ai__nope"),
        ("keyword", "x"),
        ("person", "a"),
    ):
        with pytest.raises(watchlist.WatchError):
            watchlist.add(db_session, kind=kind, value=value)
    assert watchlist.remove(db_session, company.id) and not watchlist.remove(db_session, company.id)


def test_hits_count_the_day_and_pick_the_most_relevant(db_session: Session) -> None:
    low = card(db_session, companies=["Qualcomm"], relevance=20)
    high = card(db_session, keywords=["스냅드래곤"], relevance=90)
    card(db_session, companies=["Qualcomm"], seen=NOW - timedelta(days=3))  # outside the day
    card(db_session, themes=["ai__on_device_ai"])
    watchlist.add(db_session, kind="company", value="qualcomm")
    watchlist.add(db_session, kind="theme", value="ai__on_device_ai")
    watchlist.add(db_session, kind="keyword", value="no such thing")

    hits = watchlist.hits(db_session, start=NOW - timedelta(days=1), end=NOW)

    assert [(h.kind, h.count) for h in hits] == [("company", 2), ("theme", 1)]
    assert hits[0].item_ids == [high, low]


def test_suggestions_skip_watched_and_organisations(db_session: Session) -> None:
    for _ in range(3):
        card(db_session, companies=["Apple", "ENISA"], themes=["platform_sw__device_os"])
    card(db_session, companies=["Qualcomm"])
    watchlist.add(db_session, kind="company", value="qualcomm")

    keys = [(s.kind, s.key) for s in watchlist.suggestions(db_session, now=NOW)]

    assert ("company", "apple") in keys and ("company", "enisa") not in keys
    assert ("company", "qualcomm") not in keys and ("theme", "platform_sw__device_os") in keys


def test_console_manages_the_list(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    assert console_client.get("/api/admin/watchlist").status_code == 401
    created = console_client.post(
        "/api/admin/watchlist", json={"kind": "company", "value": "qualcomm"}, headers=headers
    )
    bad = console_client.post(
        "/api/admin/watchlist", json={"kind": "company", "value": "nope"}, headers=headers
    )
    page = console_client.get("/api/admin/watchlist", headers=headers).json()

    assert created.status_code == 201 and bad.status_code == 422
    assert page["items"][0]["key"] == "qualcomm"
    assert {"key": "qualcomm", "label": "퀄컴"} in page["companies"]
    gone = console_client.delete(f"/api/admin/watchlist/{created.json()['id']}", headers=headers)
    assert gone.status_code == 204
