from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.classify.models import LabelMethod
from news_insight.classify.store import apply_labels
from news_insight.classify.taxonomy import Axis, get_taxonomy
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import Region, Track
from tests.factories import build_source

pytestmark = pytest.mark.db
REV = get_taxonomy().revision


def seed(db_session: Session) -> dict[str, int]:
    now = datetime.now(UTC)
    news = build_source(key="news", name="The Verge")
    kr = build_source(
        key="kr", region=Region.KR, language="ko", track=Track.COMMUNITY, category="dev_forum"
    )
    db_session.add_all([news, kr])
    db_session.flush()
    for source, titles in ((news, ["Galaxy S30", "OLED price"]), (kr, ["긱뉴스 글"])):
        ingest_items(
            db_session,
            source,
            [RawItem(stable_id=t, url=f"https://www.example.com/{t}", title=t) for t in titles],
            fetch_run=None,
            now=now,
            canary=True,
        )
    items = {item.title: item for item in db_session.scalars(select(Item))}
    ids = {title: item.id for title, item in items.items()}
    db_session.add_all(
        [
            ItemCard(
                item_id=ids["Galaxy S30"],
                status=CardStatus.READY,
                title_ko="갤럭시 S30 공개",
                summary_ko=["3월 출시"],
                keywords=["삼성", "갤럭시"],
                engine="agy",
                model="gemini",
                input_hash=items["Galaxy S30"].content_hash,
                attempts=0,
                generated_at=now,
            ),
            ItemCard(
                item_id=ids["긱뉴스 글"],
                status=CardStatus.READY,
                title_ko="긱뉴스 글",
                summary_ko=[],
                keywords=["커뮤니티"],
                engine="qwen",
                model="qwen",
                input_hash=items["긱뉴스 글"].content_hash,
                attempts=0,
                generated_at=now - timedelta(days=3),
            ),
            ItemCard(
                item_id=ids["OLED price"],
                status=CardStatus.FAILED,
                title_ko=None,
                summary_ko=[],
                keywords=[],
                engine="agy",
                model="gemini",
                input_hash=items["OLED price"].content_hash,
                attempts=3,
                generated_at=now,
            ),
            CardRun(
                started_at=now,
                finished_at=now,
                ready=2,
                failed=1,
                batches={"agy": 1},
                quota={"weekly": 80, "five_hour": 50},
                note=None,
            ),
        ]
    )
    db_session.flush()
    apply_labels(
        db_session,
        ids["Galaxy S30"],
        {Axis.FIELD: ["ai", "display"], Axis.PRODUCT: ["phone"], Axis.IMPACT: ["opportunity"]},
        taxonomy_rev=REV,
        method=LabelMethod.LLM,
        engine="agy",
        model="gemini",
        now=now,
    )
    apply_labels(
        db_session,
        ids["긱뉴스 글"],
        # "retired_key" stands for a node removed from the taxonomy since: never shown.
        {Axis.FIELD: ["retired_key", "devtools"], Axis.PRODUCT: [], Axis.IMPACT: ["risk"]},
        taxonomy_rev=REV,
        method=LabelMethod.LLM,
        engine="qwen",
        model="qwen",
        now=now,
    )
    return ids


def test_card_feed_shows_and_filters_taxonomy_labels(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    def titles(query: str) -> list[str]:
        response = console_client.get(f"/api/admin/cards?{query}", headers=headers)
        assert response.status_code == 200, response.text
        return [view["card"]["title_ko"] for view in response.json()["items"]]

    feed = console_client.get("/api/admin/cards?field=ai", headers=headers).json()
    card = feed["items"][0]["card"]
    assert card["fields"] == [
        {"key": "ai", "label": "온디바이스 AI·모델"},
        {"key": "display", "label": "디스플레이"},
    ]
    assert card["products"] == [{"key": "phone", "label": "스마트폰"}]
    assert card["impact"] == {"key": "opportunity", "label": "기회"}
    assert titles("field=devtools") == ["긱뉴스 글"]
    assert titles("product=phone&impact=opportunity") == ["갤럭시 S30 공개"]
    assert titles("impact=watch") == []
    community = console_client.get("/api/admin/cards?impact=risk", headers=headers).json()
    assert [f["key"] for f in community["items"][0]["card"]["fields"]] == ["devtools"]
    unknown = console_client.get("/api/admin/cards?field=retired_key", headers=headers)
    assert unknown.status_code == 422


def test_taxonomy_endpoint_lists_the_current_revision(
    console_client: TestClient, headers: dict[str, str]
) -> None:
    taxonomy = console_client.get("/api/admin/taxonomy", headers=headers).json()

    assert taxonomy["revision"] == REV
    assert taxonomy["max_fields"] == 3 and taxonomy["max_products"] == 3
    assert len(taxonomy["fields"]) == 23 and len(taxonomy["products"]) == 18
    assert taxonomy["impacts"][0] == {
        "key": "opportunity",
        "label": "기회",
        "description": taxonomy["impacts"][0]["description"],
    }


def test_card_feed_filters_and_searches(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    feed = console_client.get("/api/admin/cards", headers=headers).json()
    kr = console_client.get("/api/admin/cards?region=kr", headers=headers).json()
    by_keyword = console_client.get("/api/admin/cards?q=삼성", headers=headers).json()
    community = console_client.get("/api/admin/cards?track=community", headers=headers).json()

    assert feed["total"] == 2
    assert feed["items"][0]["card"]["title_ko"] in {"갤럭시 S30 공개", "긱뉴스 글"}
    assert [view["item"]["title"] for view in kr["items"]] == ["긱뉴스 글"]
    assert [view["card"]["title_ko"] for view in by_keyword["items"]] == ["갤럭시 S30 공개"]
    assert community["total"] == 1


def test_card_stats_and_korean_titles_on_items(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    ids = seed(db_session)

    stats = console_client.get("/api/admin/cards/stats", headers=headers).json()
    items = console_client.get("/api/admin/items?q=Galaxy", headers=headers).json()
    detail = console_client.get(f"/api/admin/items/{ids['Galaxy S30']}", headers=headers).json()

    assert (stats["ready"], stats["failed"], stats["pending"]) == (2, 1, 0)
    assert stats["ready_today"] >= 1
    assert stats["by_engine"] == {"agy": 1, "qwen": 1}
    assert stats["last_run"]["quota"] == {"weekly": 80, "five_hour": 50}
    assert items["items"][0]["title_ko"] == "갤럭시 S30 공개"
    assert detail["card"]["keywords"] == ["삼성", "갤럭시"]
    assert detail["card"]["impact"] == {"key": "opportunity", "label": "기회"}
    assert [f["key"] for f in detail["card"]["fields"]] == ["ai", "display"]
