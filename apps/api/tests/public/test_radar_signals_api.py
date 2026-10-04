"""Radar statistics that need extra fixtures on top of the shared corpus."""

from datetime import timedelta
from math import log1p
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.public.keywords import keyword_key
from news_insight.public.periods import KST
from news_insight.sources.models import Source
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
from tests.public.seed import NOW, seed_corpus

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def corpus(db_session: Session) -> dict[str, int]:
    return seed_corpus(db_session)


def radar(client: TestClient, headers: dict[str, str], **params: Any) -> Any:
    response = client.get("/api/public/radar", params={"period": "week", **params}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def add_report(
    session: Session, title: str, hours_ago: float, field: str, keywords: list[str]
) -> int:
    source = session.scalars(select(Source).where(Source.key == "verge")).one()
    ingest_items(
        session,
        source,
        [RawItem(stable_id=title, url=f"https://verge.example/{title}", title=title)],
        fetch_run=None,
        now=NOW - timedelta(hours=hours_ago),
        canary=False,
    )
    item = session.scalars(select(Item).where(Item.title == title)).one()
    session.add(
        ItemCard(
            item_id=item.id,
            status=CardStatus.READY,
            title_ko=title,
            summary_ko=[],
            keywords=keywords,
            engine="agy",
            model="gemini",
            input_hash=item.content_hash,
            attempts=0,
            generated_at=item.first_seen_at,
            field=field,
            themes=[],
            businesses=[],
            impact="watch",
            scope="dx",
            relevance=50,
            taxonomy_revision=TAXONOMY_REVISION,
        )
    )
    session.flush()
    return item.id


def test_keyword_keys_merge_spellings_and_synonyms() -> None:
    assert keyword_key("AI 에이전트") == keyword_key("AI-Agent") == "ai에이전트"
    assert keyword_key("대형 언어 모델") == keyword_key("LLM") == "llm"
    assert keyword_key("QD-OLED") == keyword_key("qd oled") == "qdoled"
    assert keyword_key("On-device AI") == "온디바이스ai"


def test_radar_merges_aliases(
    public_client: TestClient,
    public_headers: dict[str, str],
    db_session: Session,
    corpus: dict[str, int],
) -> None:
    db_session.execute(
        update(ItemCard)
        .where(ItemCard.item_id == corpus["oled-compensation repo"])
        .values(keywords=["oled", "AI Agent"])
    )
    keywords = {k["key"]: k for k in radar(public_client, public_headers)["keywords"]}
    assert keywords["ai에이전트"]["counts"][-1] == 3
    assert "aiagent" not in keywords


def test_keyword_debut_and_return(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    keywords = {k["key"]: k for k in radar(public_client, public_headers)["keywords"]}
    # oled was first reported this week, the agent keyword ten days ago: both inside 3 weeks
    assert keywords["oled"]["debut"] is True
    assert keywords["oled"]["returning"] is False
    assert keywords["ai에이전트"]["debut"] is True
    # a report 30 weeks ago makes this week's "new" oled a returning keyword
    add_report(db_session, "old oled story", 24 * 7 * 30, "display_media", ["OLED"])
    keywords = {k["key"]: k for k in radar(public_client, public_headers)["keywords"]}
    assert keywords["oled"]["state"] == "new"
    assert keywords["oled"]["returning"] is True
    assert keywords["oled"]["debut"] is False
    assert keywords["oled"]["first_ever"].startswith("2026-03")


def test_radar_engagement_counts_growth_inside_the_window(
    public_client: TestClient,
    public_headers: dict[str, str],
    db_session: Session,
    corpus: dict[str, int],
) -> None:
    repo = corpus["oled-compensation repo"]
    db_session.add_all(
        [
            ItemMetricSnapshot(
                item_id=repo, captured_at=NOW - timedelta(days=10), metrics={"stars": 10}
            ),
            ItemMetricSnapshot(
                item_id=repo,
                captured_at=NOW - timedelta(days=1),
                metrics={"stars": 110, "views": 9999},
            ),
        ]
    )
    db_session.flush()
    engagement = radar(public_client, public_headers)["engagement"]
    assert engagement["measured"] == 1
    assert engagement["themes"] == [
        {"key": "display_media__oled_microled", "score": round(log1p(100), 2), "items": 1}
    ]
    top = engagement["top"][0]
    assert (top["id"], top["metric"], top["gain"], top["current"]) == (repo, "stars", 100, 110)
    earlier = radar(public_client, public_headers, key="2026-W39")["engagement"]
    assert earlier["measured"] == 0


def test_radar_calendar_flags_a_category_spike(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    for n in range(9):
        add_report(db_session, f"quantum launch {n}", 1 + n * 0.1, "emerging_science", ["양자"])
    calendar = radar(public_client, public_headers)["calendar"]
    assert len(calendar["days"]) == 84
    today = (NOW - timedelta(hours=1)).astimezone(KST).date().isoformat()
    [anomaly] = calendar["anomalies"]
    assert (anomaly["day"], anomaly["field"], anomaly["count"]) == (today, "emerging_science", 9)
    assert anomaly["keywords"] == [{"key": "양자", "label": "양자", "count": 9}]


def test_radar_field_links_and_baseline_tracks(
    public_client: TestClient,
    public_headers: dict[str, str],
    db_session: Session,
    corpus: dict[str, int],
) -> None:
    db_session.execute(
        update(ItemCard)
        .where(ItemCard.item_id == corpus["Galaxy agent OS"])
        .values(themes=["ai_data__ai_agents", "mobile_edge__smartphone_compute"])
    )
    body = radar(public_client, public_headers)
    assert body["field_links"] == [{"a": "ai_data", "b": "mobile_edge", "count": 1, "previous": 0}]
    network = {f["key"]: f for f in body["fields"]}["network_comms"]
    assert network["baseline_tracks"]["news"] == 1
