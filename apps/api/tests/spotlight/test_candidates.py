import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item, ItemDedup
from news_insight.sources.enums import Region, Track, ValidationStage
from news_insight.sources.models import Source
from news_insight.spotlight.candidates import (
    SECTIONS,
    collect_candidates,
    window,
)
from news_insight.stories.models import Relation, Story, StoryItem
from tests.factories import build_source

pytestmark = pytest.mark.db
DAY = date(2026, 11, 4)
START, END = window(DAY)
SEEN = END - timedelta(hours=10)
NOW = END


def source(session: Session, key: str, track: Track, operator: str | None = None) -> Source:
    row = session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if row is None:
        row = build_source(
            key=key,
            name=key,
            operator=operator or f"{key} Inc.",
            track=track,
            category="dev_forum" if track is Track.COMMUNITY else "independent_media",
            region=Region.GLOBAL_EN,
            official_domain=f"{key}.com",
            validation_stage=ValidationStage.V4,
        )
        session.add(row)
        session.flush()
    return row


def item(
    session: Session,
    src: Source,
    slug: str,
    *,
    seen: datetime = SEEN,
    metrics: dict[str, int] | None = None,
    canary: bool = False,
) -> Item:
    url = f"https://{src.key}.com/{slug}"
    ingest_items(
        session,
        src,
        [
            RawItem(
                stable_id=url,
                url=url,
                title=f"{slug} headline",
                published_at=seen,
                metrics=metrics or {},
            )
        ],
        fetch_run=None,
        now=seen,
        canary=canary,
    )
    return session.scalars(select(Item).where(Item.url == url)).one()


def story(session: Session, items: list[Item], *, source_count: int | None = None) -> Story:
    row = Story(
        representative_item_id=items[0].id,
        title_ko=f"사건 {items[0].id}",
        first_seen_at=SEEN,
        last_seen_at=SEEN,
        item_count=len(items),
        source_count=source_count if source_count is not None else len(items),
        tracks=["news"],
    )
    session.add(row)
    session.flush()
    for n, member in enumerate(items):
        session.add(
            StoryItem(
                item_id=member.id,
                story_id=row.id,
                relation=Relation.SEED if n == 0 else Relation.EVENT,
                joined_at=SEEN,
            )
        )
    session.flush()
    return row


def news_story(session: Session, name: str, count: int) -> Story:
    members = [
        item(session, source(session, f"{name}-{n}", Track.NEWS), f"{name}-{n}")
        for n in range(count)
    ]
    return story(session, members)


HN = "Algolia (HN Search)"


def hn_posts(session: Session, points: list[int], *, prefix: str = "hn") -> list[Item]:
    src = source(session, "hn", Track.COMMUNITY, HN)
    return [
        item(session, src, f"{prefix}-{n}", metrics={"points": p, "comments": 0})
        for n, p in enumerate(points)
    ]


def test_window_is_0440_kst_to_0440_kst():
    assert window(date(2026, 11, 4)) == (
        datetime(2026, 11, 2, 19, 40, tzinfo=UTC),
        datetime(2026, 11, 3, 19, 40, tzinfo=UTC),
    )


def test_all_sections_present_even_if_empty(db_session: Session):
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert set(result) == set(SECTIONS)
    assert all(candidates == [] for candidates in result.values())


def test_items_outside_window_excluded(db_session: Session):
    members = [
        item(db_session, source(db_session, f"old-{n}", Track.NEWS), f"old-{n}", seen=seen)
        for n, seen in enumerate([START - timedelta(minutes=1), END, END + timedelta(hours=1)])
    ]
    story(db_session, members)
    hn_posts(db_session, [5, 5, 5, 5, 5, 5, 5, 5])
    outside = item(
        db_session,
        source(db_session, "hn", Track.COMMUNITY, HN),
        "viral-old",
        seen=START - timedelta(hours=1),
        metrics={"points": 5000, "comments": 900},
    )
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert result["news"] == []
    assert all(outside.id not in c.item_ids for c in result["community"])


def test_one_entry_per_story(db_session: Session):
    row = news_story(db_session, "launch", 3)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["news"]) == 1
    candidate = result["news"][0]
    assert candidate.key == f"story:{row.id}"
    assert candidate.cid == "n1"
    assert candidate.stat_rank == 1
    assert len(candidate.item_ids) == 3
    assert candidate.item_ids[0] == row.representative_item_id
    assert candidate.metrics == {"source_count": 3, "community_mentions": 0}
    assert candidate.score == pytest.approx(300.0)


def test_duplicate_items_excluded(db_session: Session):
    row = news_story(db_session, "dup", 3)
    posts = hn_posts(db_session, [5, 5, 5, 5, 5, 5, 5, 5, 400])
    viral = posts[-1]
    first_news = row.representative_item_id
    # the viral post and one article repeat earlier items
    db_session.execute(
        update(ItemDedup)
        .where(ItemDedup.item_id.in_([viral.id, first_news]))
        .values(duplicate_of=posts[0].id, matched_by="url")
    )
    db_session.flush()
    result = collect_candidates(db_session, day=DAY, now=NOW)
    seen_ids = {i for cs in result.values() for c in cs for i in c.item_ids}
    assert viral.id not in seen_ids
    assert first_news not in seen_ids
    assert len(result["news"][0].item_ids) == 2


def test_canary_items_excluded(db_session: Session):
    members = [
        item(db_session, source(db_session, f"can-{n}", Track.NEWS), f"can-{n}", canary=n == 0)
        for n in range(3)
    ]
    story(db_session, members)
    src = source(db_session, "hn", Track.COMMUNITY, HN)
    hn_posts(db_session, [5] * 10)
    probe = item(db_session, src, "probe", metrics={"points": 900, "comments": 0}, canary=True)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert members[0].id not in result["news"][0].item_ids
    assert result["community"] == []
    assert probe.id not in {i for c in result["community"] for i in c.item_ids}


def test_news_ranked_by_source_count(db_session: Session):
    small = news_story(db_session, "small", 3)
    big = news_story(db_session, "big", 5)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.key for c in result["news"]] == [f"story:{big.id}", f"story:{small.id}"]
    assert [(c.cid, c.stat_rank) for c in result["news"]] == [("n1", 1), ("n2", 2)]


def test_news_below_two_sources_excluded(db_session: Session):
    # three articles but one outlet: source_count 1
    lone = [item(db_session, source(db_session, "solo", Track.NEWS), f"solo-{n}") for n in range(3)]
    story(db_session, lone, source_count=1)
    # an item with no story at all
    item(db_session, source(db_session, "alone", Track.NEWS), "alone")
    pair = news_story(db_session, "pair", 2)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.key for c in result["news"]] == [f"story:{pair.id}"]


def test_news_counts_community_mentions_and_uses_best_z(db_session: Session):
    plain = news_story(db_session, "plain", 3)
    talked = news_story(db_session, "talked", 2)
    talked_ids = list(
        db_session.scalars(
            select(StoryItem.item_id)
            .where(StoryItem.story_id == talked.id)
            .order_by(StoryItem.item_id)
        )
    )
    posts = hn_posts(db_session, [5] * 8 + [400])
    # one post belongs to the event, another shares one of its articles
    db_session.add(
        StoryItem(item_id=posts[-1].id, story_id=talked.id, relation=Relation.EVENT, joined_at=SEEN)
    )
    sharing = posts[0]
    article = db_session.get(ItemDedup, talked_ids[1])
    assert article is not None
    article_key = article.url_key
    db_session.execute(
        update(ItemDedup)
        .where(ItemDedup.item_id == sharing.id)
        # a shared article is stored as a repeat of it: it still counts as a mention
        .values(link_key=article_key, duplicate_of=talked_ids[1], matched_by="link")
    )
    db_session.flush()
    result = collect_candidates(db_session, day=DAY, now=NOW)
    by_key = {c.key: c for c in result["news"]}
    assert by_key[f"story:{talked.id}"].metrics == {"source_count": 2, "community_mentions": 2}
    assert by_key[f"story:{plain.id}"].metrics["community_mentions"] == 0
    # 2 sources, 2 mentions, and the viral post's z on top
    assert 220.0 < by_key[f"story:{talked.id}"].score < 235.0
    assert by_key[f"story:{plain.id}"].stat_rank == 1  # 3 sources still outrank
    # the post is a mention of the event, not one of its news items
    assert posts[-1].id not in by_key[f"story:{talked.id}"].item_ids


def test_community_below_z_one_excluded(db_session: Session):
    posts = hn_posts(db_session, [5] * 10 + [400])
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.item_ids for c in result["community"]] == [[posts[-1].id]]
    top = result["community"][0]
    assert top.cid == "c1"
    assert top.key == f"item:{posts[-1].id}"
    assert top.metrics == {"points": 400, "comments": 0, "platform": HN}
    assert top.score >= 1.0
    assert top.url == posts[-1].url


def test_community_without_engagement_or_unknown_platform_excluded(db_session: Session):
    hn_posts(db_session, [5] * 10 + [400])
    item(db_session, source(db_session, "bare", Track.COMMUNITY, HN), "bare")
    item(
        db_session,
        source(db_session, "mystery", Track.COMMUNITY, "Nobody"),
        "mystery",
        metrics={"points": 9000},
    )
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["community"]) == 1


def test_community_posts_of_one_story_keep_the_strongest(db_session: Session):
    posts = hn_posts(db_session, [5] * 10 + [300, 400])
    story(db_session, posts[-2:], source_count=2)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.item_ids for c in result["community"]] == [[posts[-1].id]]


def test_candidate_text_comes_from_card_with_fallbacks(db_session: Session):
    row = news_story(db_session, "carded", 2)
    other = news_story(db_session, "plain", 2)
    db_session.add(
        ItemCard(
            item_id=row.representative_item_id,
            status=CardStatus.READY,
            title_ko="카드 제목",
            summary_ko=["첫째 줄", "둘째 줄"],
            keywords=[],
            engine="agy",
            model="m",
            input_hash="h",
            attempts=0,
            generated_at=SEEN,
        )
    )
    db_session.flush()
    result = collect_candidates(db_session, day=DAY, now=NOW)
    by_key = {c.key: c for c in result["news"]}
    carded = by_key[f"story:{row.id}"]
    assert (carded.title_ko, carded.summary_ko) == ("카드 제목", "첫째 줄 둘째 줄")
    plain = by_key[f"story:{other.id}"]
    assert (plain.title_ko, plain.summary_ko) == (other.title_ko, "")


def test_to_json_round_trips_plain_data(db_session: Session):
    news_story(db_session, "json", 2)
    candidate = collect_candidates(db_session, day=DAY, now=NOW)["news"][0]
    data = candidate.to_json()
    assert set(data) == {
        "cid",
        "section",
        "key",
        "item_ids",
        "title_ko",
        "summary_ko",
        "url",
        "metrics",
        "score",
        "stat_rank",
    }
    assert json.loads(json.dumps(data)) == data
