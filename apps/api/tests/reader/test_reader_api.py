from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingStatus
from news_insight.briefing.service import publish
from news_insight.cards.models import ItemCard
from tests.briefing.test_publish import DAY, FREEZE_AT, RULES, FakeClaude, seed

pytestmark = pytest.mark.db


def published(db_session: Session) -> Briefing:
    seed(db_session)
    db_session.execute(
        update(ItemCard).values(
            field="ai_data", themes=["ai_data__ai_agents"], impact="opportunity"
        )
    )
    briefing = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )
    assert briefing.status is BriefingStatus.PUBLISHED
    return briefing


def test_public_briefing_needs_no_key(db_session: Session, console_client: TestClient) -> None:
    assert console_client.get("/api/public/briefings/latest").json() is None
    published(db_session)

    latest = console_client.get("/api/public/briefings/latest")
    body = latest.json()

    assert latest.status_code == 200 and latest.headers["cache-control"].startswith("public")
    assert body["briefing_date"] == str(DAY) and body["headline"] == "헤드라인"
    assert [s["track"] for s in body["sections"]] == ["news", "research_ip", "oss", "community"]
    assert sum(len(s["items"]) for s in body["sections"]) == 8
    card = body["sections"][0]["items"][0]
    assert "engine" not in card and "source_key" not in card and card["field"] == "ai_data"
    assert body["gates_passed"] == body["gates_total"] > 0
    assert console_client.get(f"/api/public/briefings/{DAY}").status_code == 200
    assert console_client.get("/api/public/briefings/2020-01-01").status_code == 404


def test_blocked_briefings_stay_private(db_session: Session, console_client: TestClient) -> None:
    briefing = published(db_session)
    briefing.status = BriefingStatus.BLOCKED
    db_session.flush()

    assert console_client.get("/api/public/briefings/latest").json() is None
    assert console_client.get("/api/public/archive").json()["total"] == 0


def test_archive_search_taxonomy(db_session: Session, console_client: TestClient) -> None:
    published(db_session)

    archive = console_client.get("/api/public/archive").json()
    found = console_client.get("/api/public/cards", params={"q": "etnews 카드"}).json()
    topic = console_client.get("/api/public/cards", params={"theme": "ai_data__ai_agents"}).json()
    counts = console_client.get("/api/public/taxonomy").json()

    assert archive["items"][0]["headline"] == "헤드라인" and archive["items"][0]["items"] == 8
    assert [c["title_ko"] for c in found["items"]] == ["etnews 카드"]
    assert topic["total"] == 8
    assert counts["fields"] == {"ai_data": 8} and counts["themes"] == {"ai_data__ai_agents": 8}
    assert counts["businesses"] == {"mx": 8} and counts["impacts"] == {"opportunity": 8}


def test_irrelevant_cards_are_hidden(db_session: Session, console_client: TestClient) -> None:
    published(db_session)
    card = db_session.scalars(select(ItemCard).where(ItemCard.title_ko == "hn 카드")).one()
    card.scope = "irrelevant"
    db_session.flush()

    found = console_client.get("/api/public/cards", params={"q": "hn 카드"}).json()
    assert found["total"] == 0


def test_rss_feeds(db_session: Session, console_client: TestClient) -> None:
    published(db_session)

    daily = console_client.get("/api/public/feed.xml")
    topic = console_client.get("/api/public/feed.xml", params={"field": "ai_data"})

    assert daily.headers["content-type"].startswith("application/rss+xml")
    items = ET.fromstring(daily.content).findall("./channel/item")
    assert len(items) == 1 and items[0].findtext("title", "").endswith("헤드라인")
    assert items[0].findtext("link", "").endswith(f"/briefings/{DAY}")
    channel = ET.fromstring(topic.content).find("channel")
    assert channel is not None and "AI·데이터" in channel.findtext("title", "")
    assert len(channel.findall("item")) == 8
