from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from news_insight.briefing.strength import Evidence, grade
from news_insight.digest.models import Digest, DigestStatus
from news_insight.digest.schemas import DigestContent, Insight
from news_insight.digest.service import recent_insights


def ev(source: int, track: str = "news", region: str = "global_en", **kw: object) -> Evidence:
    values: dict[str, object] = {"category": "independent_media", "story_sources": 1, **kw}
    return Evidence(source_id=source, track=track, region=region, **values)  # type: ignore[arg-type]


def test_grades_follow_outlets_spread_and_vendor_share() -> None:
    wide = {1: ev(1, story_sources=19), 2: ev(2, track="research_ip", region="kr")}
    assert (s := grade([1, 2], wide)) and s.grade == "strong" and s.outlets == 19
    assert "출처 19곳" in s.reason

    narrow = {1: ev(1), 2: ev(2)}
    assert (s := grade([1, 2], narrow)) and s.grade == "weak"

    vendor = {i: ev(i, category="official_vendor", story_sources=6) for i in (1, 2)}
    assert (s := grade([1, 2], vendor)) and s.grade == "weak" and "자사 발표" in s.reason

    middle = {1: ev(1, story_sources=4), 2: ev(2)}
    assert (s := grade([1, 2], middle)) and s.grade == "medium"
    assert grade([9], middle) is None


def test_odd_engine_values_never_fail_the_digest() -> None:
    insight = Insight.model_validate(
        {
            "title": "t",
            "body": "b",
            "item_ids": [1, 2],
            "continuity": "sideways",
            "companies": ["Apple", "apple ", "", "Apple"],
        }
    )
    assert insight.continuity == "new" and insight.companies == ["Apple", "apple"]
    content = DigestContent.model_validate(
        {
            "headline": "h",
            "overview": "o",
            "tracks": [],
            "insights": [],
            "tldr": ["one", "two", "three", "four", ""],
        }
    )
    assert content.tldr == ["one", "two", "three"]


@pytest.mark.db
def test_recent_insights_gives_the_last_three_published_dates(db_session: Session) -> None:
    now = datetime(2026, 10, 6, tzinfo=UTC)
    for offset, status in (
        (1, DigestStatus.PUBLISHED),
        (2, DigestStatus.FALLBACK),
        (3, DigestStatus.PUBLISHED),
        (4, DigestStatus.PUBLISHED),
        (5, DigestStatus.PUBLISHED),
    ):
        day = date(2026, 10, 6) - timedelta(days=offset)
        db_session.add(
            Digest(
                digest_date=day,
                version=1,
                status=status,
                generated_at=now,
                window_start=now,
                window_end=now,
                item_count=1,
                input_hash=f"h{offset}",
                content={"headline": f"h{offset}", "insights": [{"title": f"i{offset}"}]},
            )
        )
    db_session.flush()

    previous = recent_insights(db_session, before=date(2026, 10, 6))

    assert [p["date"] for p in previous] == ["2026-10-05", "2026-10-03", "2026-10-02"]
    assert previous[0] == {"date": "2026-10-05", "headline": "h1", "insights": ["i1"]}
