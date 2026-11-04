import math
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.sources.enums import Region, Track, ValidationStage
from news_insight.spotlight.scoring import (
    MIN_SAMPLE,
    PLATFORM_METRICS,
    PlatformStats,
    engagement,
    platform_stats,
    velocity,
    zscore,
)
from tests.factories import build_source

AT = datetime(2026, 11, 4, 19, 40, tzinfo=UTC)


def test_hn_sums_points_and_comments():
    assert engagement("Algolia (HN Search)", {"points": 400, "comments": 12}) == 412


def test_unknown_operator_is_none():
    assert engagement("Nobody", {"points": 3}) is None


def test_missing_keys_is_none():
    assert engagement("Algolia (HN Search)", {"stars": 3}) is None
    assert engagement("Algolia (HN Search)", {}) is None


def test_partial_keys_sum_what_exists():
    assert engagement("Bluesky Social PBC", {"likes": 5, "reposts": 2}) == 7


def test_huggingface_prefers_trending_over_likes():
    assert engagement("Hugging Face", {"trending": 40, "likes": 900}) == 40
    assert engagement("Hugging Face", {"likes": 900}) == 900


def test_github_trending_uses_daily_stars():
    assert engagement("GitHub", {"stars": 90000, "trending_stars_daily": 350}) == 350


def test_v2ex_and_stack_families_map_score_answers():
    for operator in ("V2EX", "V2EX Python", "V2EX 云计算", "Stack Exchange Inc."):
        assert PLATFORM_METRICS[operator] == ("score", "answers")


def test_hours_floor_two():
    at = datetime(2026, 11, 4, 19, 40, tzinfo=UTC)
    assert velocity(100, at - timedelta(minutes=30), at, at) == pytest.approx(math.log1p(50))


def test_future_published_at_uses_floor():
    at = datetime(2026, 11, 4, 19, 40, tzinfo=UTC)
    assert velocity(100, at + timedelta(hours=9), at, at) == pytest.approx(math.log1p(50))


def test_velocity_uses_published_hours_and_falls_back_to_first_seen():
    assert velocity(100, AT - timedelta(hours=10), AT - timedelta(hours=1), AT) == pytest.approx(
        math.log1p(10)
    )
    assert velocity(100, None, AT - timedelta(hours=5), AT) == pytest.approx(math.log1p(20))


def test_negative_score_is_clamped_to_zero():
    assert engagement("Stack Exchange Inc.", {"score": -3, "answers": 1}) == 0
    assert engagement("V2EX", {"score": -9}) == 0
    # Without the clamp log1p(-3 / 10 ... -5) would raise for values <= -2 * hours.
    assert velocity(-50, AT - timedelta(hours=10), AT, AT) == 0.0


def test_small_platform_uses_fallback():
    fb = PlatformStats(mean=1.0, std=1.0, n=500)
    assert zscore(3.0, PlatformStats(mean=0.0, std=1.0, n=10), fb) == pytest.approx(2.0)


def test_missing_platform_uses_fallback():
    fb = PlatformStats(mean=1.0, std=2.0, n=500)
    assert zscore(5.0, None, fb) == pytest.approx(2.0)


def test_large_platform_uses_own_stats():
    own = PlatformStats(mean=4.0, std=1.0, n=MIN_SAMPLE)
    assert zscore(6.0, own, PlatformStats(0.0, 10.0, 500)) == pytest.approx(2.0)


def test_zero_std_is_zero():
    assert zscore(5.0, PlatformStats(2.0, 0.0, 100), PlatformStats(0, 1, 100)) == 0.0


def _item(
    session: Session,
    key: str,
    operator: str,
    track: Track,
    metrics: dict[str, int],
    *,
    seen: datetime = AT - timedelta(hours=10),
) -> Item:
    source = build_source(
        key=key,
        name=key,
        operator=operator,
        track=track,
        category="dev_forum",
        region=Region.GLOBAL_EN,
        official_domain=f"{key}.com",
        validation_stage=ValidationStage.V4,
    )
    session.add(source)
    session.flush()
    url = f"https://{key}.com/post"
    ingest_items(
        session,
        source,
        [
            RawItem(
                stable_id=url,
                url=url,
                title=key,
                published_at=seen,
                metrics=metrics,
            )
        ],
        fetch_run=None,
        now=seen,
        canary=True,
    )
    return session.scalars(select(Item).where(Item.url == url)).one()


@pytest.mark.db
def test_platform_stats_uses_latest_snapshot(db_session: Session):
    item = _item(db_session, "hn-a", "Algolia (HN Search)", Track.COMMUNITY, {"points": 10})
    db_session.add(
        ItemMetricSnapshot(
            item_id=item.id, captured_at=AT - timedelta(hours=1), metrics={"points": 100}
        )
    )
    db_session.flush()
    per_platform, overall = platform_stats(db_session, at=AT)
    # 100 points, published 10 hours before AT: only the later snapshot counts.
    expected = math.log1p(100 / 10)
    hn = per_platform["Algolia (HN Search)"]
    assert hn.n == 1
    assert hn.mean == pytest.approx(expected)
    assert hn.std == 0.0
    assert overall.n == 1
    assert overall.mean == pytest.approx(expected)


@pytest.mark.db
def test_platform_stats_ignores_snapshots_after_at(db_session: Session):
    item = _item(db_session, "hn-b", "Algolia (HN Search)", Track.COMMUNITY, {"points": 10})
    db_session.add(
        ItemMetricSnapshot(
            item_id=item.id, captured_at=AT + timedelta(hours=1), metrics={"points": 999}
        )
    )
    db_session.flush()
    per_platform, _ = platform_stats(db_session, at=AT)
    assert per_platform["Algolia (HN Search)"].mean == pytest.approx(math.log1p(10 / 10))


@pytest.mark.db
def test_platform_stats_groups_by_operator_and_scopes_overall(db_session: Session):
    _item(db_session, "hn-c", "Algolia (HN Search)", Track.COMMUNITY, {"points": 30})
    _item(db_session, "dev-c", "DEV Community", Track.COMMUNITY, {"reactions": 50})
    _item(db_session, "gh-c", "GitHub", Track.OSS, {"trending_stars_daily": 70})
    # News items, items without a mapping or without usable metrics, and stale items are skipped.
    _item(db_session, "news-c", "Algolia (HN Search)", Track.NEWS, {"points": 500})
    _item(db_session, "other-c", "Nobody", Track.COMMUNITY, {"points": 500})
    _item(db_session, "empty-c", "DEV Community", Track.COMMUNITY, {})
    _item(
        db_session,
        "old-c",
        "DEV Community",
        Track.COMMUNITY,
        {"reactions": 500},
        seen=AT - timedelta(days=9),
    )
    per_platform, overall = platform_stats(db_session, at=AT, days=7)
    assert set(per_platform) == {"Algolia (HN Search)", "DEV Community", "GitHub"}
    assert per_platform["DEV Community"].n == 1
    assert overall.n == 3
    values = [math.log1p(30 / 10), math.log1p(50 / 10), math.log1p(70 / 10)]
    mean = sum(values) / 3
    assert overall.mean == pytest.approx(mean)
    assert overall.std == pytest.approx(math.sqrt(sum((v - mean) ** 2 for v in values) / 3))


@pytest.mark.db
def test_platform_stats_survives_negative_score(db_session: Session):
    _item(db_session, "se-neg", "Stack Exchange Inc.", Track.COMMUNITY, {"score": -30})
    _item(db_session, "se-pos", "Stack Exchange Inc.", Track.COMMUNITY, {"score": 20})
    per_platform, overall = platform_stats(db_session, at=AT)
    stack = per_platform["Stack Exchange Inc."]
    assert stack.n == 2
    assert stack.mean == pytest.approx(math.log1p(20 / 10) / 2)
    assert overall.n == 2


@pytest.mark.db
def test_platform_stats_empty_window(db_session: Session):
    per_platform, overall = platform_stats(db_session, at=AT)
    assert per_platform == {}
    assert overall == PlatformStats(mean=0.0, std=0.0, n=0)


@pytest.mark.db
def test_platform_stats_gives_hf_daily_papers_a_distribution_outside_the_pool(db_session: Session):
    _item(db_session, "hn-p", "Algolia (HN Search)", Track.COMMUNITY, {"points": 30})
    _item(db_session, "hfp-1", "Hugging Face Daily Papers", Track.RESEARCH_IP, {"upvotes": 20})
    _item(db_session, "hfp-2", "Hugging Face Daily Papers", Track.RESEARCH_IP, {"upvotes": 40})
    per_platform, overall = platform_stats(db_session, at=AT)
    assert per_platform["Hugging Face Daily Papers"].n == 2
    assert overall.n == 1  # the pool stays community and open source
