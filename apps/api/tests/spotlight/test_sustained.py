from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import BenchmarkScore, BenchmarkSnapshot
from news_insight.benchmarks.sources import lmarena
from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.sources.enums import Track
from news_insight.spotlight import sustained as sustained_module
from news_insight.spotlight.candidates import SECTIONS, window
from news_insight.spotlight.models import (
    Spotlight,
    SpotlightEntry,
    SpotlightFreeze,
    SpotlightStatus,
)
from news_insight.spotlight.sustained import collect_sustained, span
from tests.spotlight.test_candidates import ai_card, card, item, ref, source, story

pytestmark = pytest.mark.db
DAY = date(2026, 11, 4)
START, END = window(DAY)
# three distinct KST days inside the seven-day span
DAYS = [END - timedelta(hours=10), END - timedelta(hours=34), END - timedelta(hours=58)]


def spread(
    session: Session, name: str, seen: list[datetime], track: Track = Track.NEWS
) -> list[Item]:
    return [
        item(session, source(session, f"{name}-{n}", track), f"{name}-{n}", seen=at)
        for n, at in enumerate(seen)
    ]


def test_span_is_seven_kst_dates_up_to_the_window_end():
    # 2026-10-29 00:00 KST up to 2026-11-04 04:40 KST
    assert span(DAY) == (datetime(2026, 10, 28, 15, 0, tzinfo=UTC), END)


def test_every_section_present_even_if_empty(db_session: Session):
    result = collect_sustained(db_session, day=DAY)
    assert set(result) == set(SECTIONS)
    assert all(found == [] for found in result.values())


def test_a_story_needs_three_distinct_days(db_session: Session):
    lasting = story(db_session, spread(db_session, "lasting", DAYS))
    # two items on one day and one the day before: two days only
    brief = story(db_session, spread(db_session, "brief", [DAYS[0], DAYS[0], DAYS[1]]))
    result = collect_sustained(db_session, day=DAY)
    keys = [c.key for c in result["news"]]
    assert keys == [f"story:{lasting.id}"]
    assert f"story:{brief.id}" not in keys
    (candidate,) = result["news"]
    assert candidate.group == "sustained"
    assert candidate.cid == "ns1"
    assert candidate.metrics == {
        "source_count": 3,
        "community_mentions": 0,
        "days_active": 3,
        "first_seen": "2026-11-01",
    }
    assert candidate.score == pytest.approx(3 * 100 + 3 * 20)


def test_a_story_older_than_the_span_does_not_count_those_days(db_session: Session):
    old = END - timedelta(days=8)
    row = story(db_session, spread(db_session, "old", [DAYS[0], DAYS[1], old]))
    assert f"story:{row.id}" not in {c.key for c in collect_sustained(db_session, day=DAY)["news"]}


def test_story_sections_follow_their_cards(db_session: Session):
    launch = story(db_session, spread(db_session, "launch", DAYS))
    card(db_session, db_session.get(Item, launch.representative_item_id), "launch")  # type: ignore[arg-type]
    model = story(db_session, spread(db_session, "model", DAYS))
    ai_card(db_session, db_session.get(Item, model.representative_item_id), "ecosystem")  # type: ignore[arg-type]
    result = collect_sustained(db_session, day=DAY)
    assert [c.key for c in result["product"]] == [f"story:{launch.id}"]
    assert [c.key for c in result["ai"]] == [f"story:{model.id}"]
    assert result["ai"][0].cid == "as1"


def test_community_threads_count_their_community_days(db_session: Session):
    posts = spread(db_session, "thread", DAYS, Track.COMMUNITY)
    thread = story(db_session, posts)
    result = collect_sustained(db_session, day=DAY)
    (candidate,) = result["community"]
    assert candidate.key == f"story:{thread.id}"
    assert candidate.metrics["community_mentions"] == 3
    # a news story with one community post a day for two days is not a lasting thread
    news = spread(db_session, "mixed", DAYS)
    chat = spread(db_session, "chat", DAYS[:2], Track.COMMUNITY)
    mixed = story(db_session, [*news, *chat])
    keys = {c.key for c in collect_sustained(db_session, day=DAY)["community"]}
    assert f"story:{mixed.id}" not in keys


def snapshot(session: Session, target: Item, at: datetime, **metrics: Any) -> None:
    session.add(ItemMetricSnapshot(item_id=target.id, captured_at=at, metrics=metrics))
    session.flush()


def test_oss_needs_trending_on_three_days(db_session: Session):
    daily = source(db_session, "github-trending-repositories-daily", Track.OSS, "GitHub")
    weekly = source(db_session, "github-trending-repositories-weekly", Track.OSS, "GitHub")
    steady = item(db_session, daily, "steady", seen=DAYS[2], metrics={"rank": 8})
    snapshot(db_session, steady, DAYS[1], rank=4)
    # the same repo on the weekly list on the third day folds in
    twin = item(db_session, weekly, "steady-w", seen=DAYS[0], metrics={"rank": 2})
    ref(db_session, steady, "github", "acme/steady")
    ref(db_session, twin, "github", "acme/steady")
    short = item(db_session, daily, "short", seen=DAYS[1], metrics={"rank": 1})
    snapshot(db_session, short, DAYS[0], rank=1, stars=5)
    result = collect_sustained(db_session, day=DAY)
    (candidate,) = result["oss"]
    assert candidate.key == f"item:{steady.id}"
    assert candidate.item_ids == [steady.id, twin.id]
    assert candidate.metrics["days_active"] == 3
    assert candidate.metrics["best_rank"] == 2
    assert candidate.metrics["basis"] == "github_daily"
    assert candidate.metrics["first_seen"] == "2026-11-01"
    assert candidate.score == pytest.approx(3 * 20 + (30 - 2))
    assert candidate.cid == "os1"


def paper(session: Session, slug: str, arxiv: str) -> Item:
    row = item(session, source(session, "arxiv", Track.RESEARCH_IP), slug, seen=DAYS[2])
    ref(session, row, "arxiv", arxiv)
    return row


def mention(session: Session, name: str, arxiv: str, seen: datetime) -> None:
    post = item(session, source(session, name, Track.COMMUNITY), name, seen=seen)
    ref(session, post, "arxiv", arxiv)


def test_research_needs_two_days_or_three_mentions(db_session: Session):
    two_days = paper(db_session, "two-days", "2611.00001")
    mention(db_session, "a", "2611.00001", DAYS[0])
    mention(db_session, "b", "2611.00001", DAYS[1])
    one_day = paper(db_session, "one-day", "2611.00002")
    mention(db_session, "c", "2611.00002", DAYS[0])
    mention(db_session, "d", "2611.00002", DAYS[0])
    crowd = paper(db_session, "crowd", "2611.00003")
    for name in ("e", "f", "g"):
        mention(db_session, name, "2611.00003", DAYS[0])
    result = collect_sustained(db_session, day=DAY)
    by_key = {c.key: c for c in result["research"]}
    assert set(by_key) == {f"item:{two_days.id}", f"item:{crowd.id}"}
    assert f"item:{one_day.id}" not in by_key
    assert by_key[f"item:{two_days.id}"].metrics == {
        "mentions": 2,
        "days_active": 2,
        "first_seen": "2026-11-02",
    }
    # 2 × 10 + 2 × 20 = 60 against 3 × 10 + 1 × 20 = 50
    assert [c.key for c in result["research"]] == [f"item:{two_days.id}", f"item:{crowd.id}"]


def board(session: Session, at: datetime, models: list[str]) -> None:
    """An LMArena text board snapshot, best first."""
    count = session.query(BenchmarkSnapshot).count()
    snap = BenchmarkSnapshot(
        site=lmarena.SITE, release="r", fetched_at=at, sha256=f"s{count}", raw={}
    )
    session.add(snap)
    session.flush()
    for n, model in enumerate(models):
        session.add(
            BenchmarkScore(
                snapshot_id=snap.id,
                site=lmarena.SITE,
                board="text",
                model_raw=model,
                metric="rating",
                value=1500.0 - n,
                extra={},
            )
        )
    session.flush()


def test_ai_takes_models_that_held_a_top_five_place(db_session: Session):
    top = ["Alpha 2", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]
    board(db_session, END - timedelta(days=9), top)  # current when the span began
    board(db_session, END - timedelta(days=4), ["Alpha 2", "Zeta", "Beta", "Gamma", "Delta"])
    board(db_session, END - timedelta(hours=5), ["Beta", "Alpha 2", "Gamma", "Delta", "Zeta"])
    result = collect_sustained(db_session, day=DAY)
    by_key = {c.key: c for c in result["ai"]}
    # Epsilon fell out of the top five, Zeta was not in it at first
    assert set(by_key) == {"model:alpha-2", "model:beta", "model:gamma", "model:delta"}
    alpha = by_key["model:alpha-2"]
    assert alpha.item_ids == []
    assert alpha.title_ko == "Alpha 2 — LMArena text 2위"
    assert alpha.metrics["basis"] == "benchmark"
    assert (alpha.metrics["rank"], alpha.metrics["best_rank"]) == (2, 1)
    assert alpha.metrics["days_active"] == 7
    assert result["ai"][0].key == "model:beta"  # rank 1 now


def test_ai_holders_need_a_three_day_span(db_session: Session):
    # 11-03 08:40 KST to 11-04 04:40 KST: two KST dates
    board(db_session, END - timedelta(hours=20), ["Alpha", "Beta"])
    board(db_session, END - timedelta(hours=5), ["Alpha", "Beta"])
    assert collect_sustained(db_session, day=DAY)["ai"] == []


def published(session: Session, day: date, rows: list[tuple[str, str, int]]) -> None:
    freeze = SpotlightFreeze(spotlight_date=day, frozen_at=END, candidates={})
    session.add(freeze)
    session.flush()
    spotlight = Spotlight(
        spotlight_date=day,
        status=SpotlightStatus.PUBLISHED,
        model="m",
        headline="",
        benchmark_note="",
        freeze_id=freeze.id,
        generated_at=END,
    )
    session.add(spotlight)
    session.flush()
    for section, key, rank in rows:
        session.add(
            SpotlightEntry(
                spotlight_id=spotlight.id,
                section=section,
                rank=rank,
                stat_rank=rank,
                key=key,
                item_ids=[rank],
                title_ko=f"{key} {day}",
                summary="요약",
                why_hot="",
                metrics={"source_count": 4},
            )
        )
    session.flush()


def test_what_the_spotlight_listed_on_two_earlier_days_returns(db_session: Session):
    published(db_session, DAY - timedelta(days=1), [("news", "story:1", 3), ("news", "story:2", 1)])
    published(db_session, DAY - timedelta(days=3), [("news", "story:1", 1), ("oss", "item:9", 1)])
    published(db_session, DAY - timedelta(days=7), [("news", "story:2", 1)])  # too long ago
    result = collect_sustained(db_session, day=DAY)
    (candidate,) = result["news"]
    assert candidate.key == "story:1"
    assert candidate.title_ko == f"story:1 {DAY - timedelta(days=1)}"  # the latest listing
    assert candidate.metrics == {
        "source_count": 4,
        "days_active": 2,
        "first_seen": (DAY - timedelta(days=3)).isoformat(),
        "listed_days": 2,
    }
    assert result["oss"] == []


def test_a_failed_part_leaves_the_others(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    def broken(session: Session, **_: Any) -> list[Any]:
        raise RuntimeError("no leaderboards")

    monkeypatch.setattr(sustained_module, "top_holders", broken)
    lasting = story(db_session, spread(db_session, "lasting", DAYS))
    result = collect_sustained(db_session, day=DAY)
    assert [c.key for c in result["news"]] == [f"story:{lasting.id}"]
    assert result["ai"] == []


def test_kst_days_are_counted_not_utc_days(db_session: Session):
    # 00:30 and 23:30 KST of one KST day are two UTC days
    base = datetime(2026, 11, 2, 15, 30, tzinfo=UTC)  # 11-03 00:30 KST
    seen = [base, base + timedelta(hours=23), base - timedelta(hours=24 * 2)]
    row = story(db_session, spread(db_session, "kst", seen))
    assert f"story:{row.id}" not in {c.key for c in collect_sustained(db_session, day=DAY)["news"]}


def test_ai_holders_count_kst_dates(db_session: Session):
    # 2026-11-01 23:30 KST is 14:30 UTC: by UTC dates the span would reach back one day less
    first = datetime(2026, 11, 1, 14, 30, tzinfo=UTC)
    board(db_session, first, ["Alpha", "Beta"])
    board(db_session, END - timedelta(hours=5), ["Alpha", "Beta"])
    # 11-01, 11-02, 11-03, 11-04 KST (END is 11-04 04:40 KST)
    by_key = {c.key: c for c in collect_sustained(db_session, day=DAY)["ai"]}
    assert by_key["model:alpha"].metrics["days_active"] == 4
