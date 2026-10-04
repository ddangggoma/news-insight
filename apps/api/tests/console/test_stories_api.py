from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.review.models import RelevanceReview, Verdict
from news_insight.sources.enums import Track
from news_insight.stories.service import cluster
from news_insight.taxonomy.catalog import TAXONOMY_REVISION
from tests.factories import build_source
from tests.stories.test_cluster import scope_for

pytestmark = pytest.mark.db


def seed(db_session: Session) -> dict[str, int]:
    now = datetime.now(UTC)
    specs = [
        (
            "verge",
            Track.NEWS,
            "https://www.verge.com/1",
            "삼성전자, 갤럭시 S30 공개…온디바이스 AI 탑재",
            ["삼성전자"],
            "dx",
            ["mx"],
            80,
            None,
        ),
        (
            "etnews",
            Track.NEWS,
            "https://www.etnews.com/1",
            "삼성전자 갤럭시 S30 공개, 온디바이스 AI 탑재했다",
            ["삼성전자"],
            "dx",
            ["mx"],
            70,
            None,
        ),
        (
            "arxiv",
            Track.RESEARCH_IP,
            "https://arxiv.org/abs/2610.00001v1",
            "경량 온디바이스 LLM 양자화 기법",
            ["양자화"],
            "dx_dependency",
            [],
            60,
            None,
        ),
        (
            "hn",
            Track.COMMUNITY,
            "https://news.ycombinator.com/item?id=1",
            "Show HN: 양자화 구현",
            ["양자화"],
            "dx",
            [],
            50,
            "https://arxiv.org/abs/2610.00001 implementation",
        ),
        (
            "politics",
            Track.NEWS,
            "https://www.example.com/p",
            "국회 본회의 일정 확정",
            ["국회"],
            "irrelevant",
            [],
            5,
            None,
        ),
    ]
    ids = {}
    for key, track, url, title, keywords, scope, businesses, relevance, summary in specs:
        source = build_source(key=key, name=key, track=track, official_domain=f"{key}.com")
        db_session.add(source)
        db_session.flush()
        ingest_items(
            db_session,
            source,
            [RawItem(stable_id=url, url=url, title=title, summary=summary)],
            fetch_run=None,
            now=now,
            canary=True,
        )
        item = db_session.scalars(select(Item).where(Item.url == url)).one()
        ids[key] = item.id
        db_session.add(
            ItemCard(
                item_id=item.id,
                status=CardStatus.READY,
                title_ko=title,
                summary_ko=[],
                keywords=keywords,
                engine="agy",
                model="m",
                input_hash=item.content_hash,
                attempts=0,
                generated_at=now,
                scope=scope,
                signal_type="launch" if businesses else None,
                relevance=relevance,
                field="platform_sw",
                taxonomy_revision=TAXONOMY_REVISION,
            )
        )
    db_session.flush()
    cluster(scope_for(db_session), now=now)
    return ids


def test_card_feed_filters_by_classification_and_dedups_stories(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    relevant = console_client.get("/api/admin/cards?scope=relevant", headers=headers).json()
    mx = console_client.get("/api/admin/cards?signal_type=launch", headers=headers).json()
    dedup = console_client.get(
        "/api/admin/cards?signal_type=launch&dedup=true", headers=headers
    ).json()

    assert relevant["total"] == 4
    assert mx["total"] == 2 and dedup["total"] == 1
    story = dedup["items"][0]["story"]
    assert (story["item_count"], story["source_count"], story["is_representative"]) == (2, 2, True)
    assert dedup["items"][0]["card"]["scope"] == "dx"


def test_stories_and_cross_track_signals(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    seed(db_session)

    stories = console_client.get("/api/admin/stories?min_size=2", headers=headers).json()
    signals = console_client.get("/api/admin/signals", headers=headers).json()

    assert stories["total"] == 1
    assert stories["items"][0]["title_ko"] == "삼성전자, 갤럭시 S30 공개…온디바이스 AI 탑재"
    assert len(stories["items"][0]["members"]) == 2
    assert [(chain["kind"], chain["value"], chain["tracks"]) for chain in signals] == [
        ("arxiv", "2610.00001", ["research_ip", "community"])
    ]


def test_review_stats_report_classifier_agreement(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    ids = seed(db_session)
    now = datetime.now(UTC)
    for key, verdict in (
        ("verge", Verdict.RELEVANT),
        ("politics", Verdict.IRRELEVANT),
        ("hn", Verdict.IRRELEVANT),
    ):
        db_session.add(RelevanceReview(item_id=ids[key], verdict=verdict, reviewed_at=now))
    db_session.flush()

    classifier = console_client.get("/api/admin/reviews/stats", headers=headers).json()[
        "classifier"
    ]

    assert (classifier["tp"], classifier["fp"], classifier["fn"], classifier["tn"]) == (1, 1, 0, 1)
    assert classifier["precision"] == 0.5 and classifier["accuracy"] == pytest.approx(2 / 3)
