from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.digest.bundle import build_bundle, digest_window
from news_insight.digest.schemas import (
    DigestContent,
    fallback_content,
    inline_schema,
    validate_content,
)
from news_insight.sources.enums import Track
from tests.factories import build_source

START, END = digest_window(date(2026, 10, 4))


def test_window_is_the_previous_kst_day() -> None:
    assert (
        datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        datetime(2026, 10, 3, 15, 0, tzinfo=UTC),
    ) == (START, END)


@pytest.mark.db
def test_bundle_groups_window_items_by_track_and_category(db_session: Session) -> None:
    news = build_source(key="news", name="The Verge")
    oss = build_source(key="oss", name="GitHub", track=Track.OSS, category="oss_trend")
    db_session.add_all([news, oss])
    db_session.flush()
    inside = START + timedelta(hours=3)
    ingest_items(
        db_session,
        news,
        [
            RawItem(
                stable_id="a", url="https://www.example.com/a", title="In window", summary="s" * 400
            )
        ],
        fetch_run=None,
        now=inside,
        canary=True,
    )
    ingest_items(
        db_session,
        news,
        [RawItem(stable_id="b", url="https://www.example.com/b", title="Too old")],
        fetch_run=None,
        now=START - timedelta(hours=1),
        canary=True,
    )
    ingest_items(
        db_session,
        oss,
        [
            RawItem(stable_id="low", url="https://github.com/l", title="low", metrics={"stars": 5}),
            RawItem(
                stable_id="high", url="https://github.com/h", title="high", metrics={"stars": 900}
            ),
        ],
        fetch_run=None,
        now=inside,
        canary=True,
    )

    bundle = build_bundle(db_session, start=START, end=END)

    tracks = {section["track"]: section for section in bundle.payload["tracks"]}
    assert bundle.item_count == 3
    assert set(tracks) == {"news", "oss"}
    assert [item["title"] for item in tracks["oss"]["categories"][0]["items"]] == ["high", "low"]
    news_item = tracks["news"]["categories"][0]["items"][0]
    assert news_item["source"] == "The Verge"
    assert len(news_item["summary"]) <= 280


def content(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "headline": "헤드라인",
        "overview": "개요",
        "tracks": [
            {
                "track": "news",
                "summary": "요약",
                "categories": [
                    {
                        "category": "independent_media",
                        "headline": "범주",
                        "points": [
                            {"text": "근거 있음", "item_ids": [1]},
                            {"text": "근거 없음", "item_ids": [99]},
                        ],
                    }
                ],
            }
        ],
        "insights": [
            {"title": "두 출처", "body": "b", "item_ids": [1, 2]},
            {"title": "한 출처", "body": "b", "item_ids": [1, 1]},
        ],
    }
    base.update(overrides)
    return base


def test_validation_drops_unsupported_claims() -> None:
    validated = validate_content(content(), known_ids={1, 2})

    assert validated is not None
    assert [point.text for point in validated.tracks[0].categories[0].points] == ["근거 있음"]
    assert [insight.title for insight in validated.insights] == ["두 출처"]


def test_validation_fails_when_nothing_is_supported() -> None:
    assert validate_content(content(), known_ids={42}) is None
    assert validate_content({"headline": "x"}, known_ids={1}) is None


def test_inline_schema_has_no_references() -> None:
    schema = inline_schema(DigestContent)

    assert "$defs" not in schema
    assert "$ref" not in str(schema)
    assert schema["properties"]["tracks"]["items"]["properties"]["track"]["enum"] == [
        "news",
        "community",
        "research_ip",
        "oss",
    ]


def test_fallback_lists_top_titles() -> None:
    payload = {
        "tracks": [
            {
                "track": "news",
                "item_count": 2,
                "categories": [
                    {
                        "category": "independent_media",
                        "items": [{"id": 7, "title": "A"}, {"id": 8, "title": "B"}],
                    }
                ],
            }
        ]
    }
    from news_insight.digest.bundle import Bundle

    result = fallback_content(
        Bundle(payload=payload, item_ids={7, 8}, item_count=2), reason="claude failed"
    )

    assert result.tracks[0].categories[0].points[0].text == "A"
    assert result.insights == []
    assert "claude failed" not in result.overview


@pytest.mark.db
def test_bundle_drops_off_topic_items_and_keeps_one_item_per_story(db_session: Session) -> None:
    from sqlalchemy import select as sa_select

    from news_insight.cards.models import CardStatus, ItemCard
    from news_insight.content.models import Item
    from news_insight.stories.models import Relation, Story, StoryItem

    source = build_source(key="news", name="News")
    db_session.add(source)
    db_session.flush()
    inside = START + timedelta(hours=3)
    ingest_items(
        db_session,
        source,
        [
            RawItem(stable_id=k, url=f"https://www.example.com/{k}", title=k)
            for k in ("rep", "dup", "politics", "fab")
        ],
        fetch_run=None,
        now=inside,
        canary=True,
    )
    items = {item.title: item for item in db_session.scalars(sa_select(Item))}
    for title, scope in (
        ("rep", "dx"),
        ("dup", "dx"),
        ("politics", "irrelevant"),
        ("fab", "excluded"),
    ):
        db_session.add(
            ItemCard(
                item_id=items[title].id,
                status=CardStatus.READY,
                title_ko=f"{title} 카드",
                summary_ko=[],
                keywords=[],
                engine="agy",
                model="m",
                input_hash=items[title].content_hash,
                attempts=0,
                generated_at=inside,
                scope=scope,
                businesses=["mx"],
            )
        )
    story = Story(
        representative_item_id=items["rep"].id,
        title_ko="rep",
        first_seen_at=inside,
        last_seen_at=inside,
        item_count=2,
        source_count=2,
        tracks=["news"],
        max_relevance=80,
    )
    db_session.add(story)
    db_session.flush()
    for title in ("rep", "dup"):
        db_session.add(
            StoryItem(
                item_id=items[title].id,
                story_id=story.id,
                relation=Relation.NEAR,
                similarity=0.9,
                joined_at=inside,
            )
        )
    db_session.flush()

    bundle = build_bundle(db_session, start=START, end=END)

    entries = [
        item
        for track in bundle.payload["tracks"]
        for cat in track["categories"]
        for item in cat["items"]
    ]
    assert [entry["title"] for entry in entries] == ["rep"]
    assert entries[0]["covered_by_sources"] == 2 and entries[0]["businesses"] == ["mx"]
    assert entries[0]["title_ko"] == "rep 카드"
