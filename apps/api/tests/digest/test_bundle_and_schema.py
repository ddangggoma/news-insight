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
