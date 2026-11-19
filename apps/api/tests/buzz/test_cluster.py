from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.buzz.cluster import run
from news_insight.buzz.models import BuzzCluster, BuzzClusterItem, BuzzItemKeys
from tests.buzz.helpers import FixedHeat, news, post

pytestmark = pytest.mark.db
NOW = datetime(2026, 11, 19, 3, 0, tzinfo=UTC)
ARTICLE = "https://www.example-vendor.com/blog/new-chip-announced"


def live(db_session: Session) -> list[BuzzCluster]:
    return list(
        db_session.scalars(
            select(BuzzCluster).where(BuzzCluster.merged_into.is_(None)).order_by(BuzzCluster.id)
        )
    )


def three_platforms(db_session: Session, when: datetime) -> None:
    post(db_session, "mastodon", 1, when=when, link=ARTICLE, title="Wow, look at this chip")
    post(db_session, "bluesky", 2, when=when + timedelta(minutes=5), link=ARTICLE)
    post(db_session, "hn", 3, when=when + timedelta(minutes=9), link=ARTICLE)


def test_a_story_only_the_community_has_is_breaking(db_session: Session) -> None:
    three_platforms(db_session, NOW - timedelta(minutes=40))

    stats = run(db_session, now=NOW, heat=FixedHeat(0.6))

    (cluster,) = live(db_session)
    assert (cluster.author_count, cluster.platform_count, cluster.human_posts) == (3, 3, 3)
    assert cluster.platforms == ["bluesky", "fediverse", "hn"]
    assert cluster.heat == pytest.approx(1.8)
    assert cluster.score == pytest.approx(10 * 3 + 4 * 3 + 5 * 1.8)
    assert cluster.crossed_at == NOW and cluster.breaking and cluster.breaking_at == NOW
    assert cluster.news_item_ids == [] and cluster.news_caught_up_at is None
    assert (stats.crossed, stats.breaking) == (1, 1)


def test_news_that_came_later_catches_up_and_earlier_news_is_no_breaking(
    db_session: Session,
) -> None:
    three_platforms(db_session, NOW - timedelta(minutes=40))
    run(db_session, now=NOW, heat=FixedHeat(0.6))
    report = news(db_session, 1, when=NOW + timedelta(minutes=20), url=ARTICLE, title="New chip")

    run(db_session, now=NOW + timedelta(minutes=30), heat=FixedHeat(0.6))

    (cluster,) = live(db_session)
    assert cluster.breaking and cluster.news_item_ids == [report.id]
    assert cluster.news_caught_up_at == report.first_seen_at


def test_a_story_the_news_already_told_is_buzz_but_not_breaking(db_session: Session) -> None:
    report = news(
        db_session, 1, when=NOW - timedelta(hours=2), url=ARTICLE, title="Vendor announces chip"
    )
    three_platforms(db_session, NOW - timedelta(minutes=40))

    run(db_session, now=NOW, heat=FixedHeat(0.6))

    (cluster,) = live(db_session)
    assert cluster.crossed_at == NOW and not cluster.breaking
    assert cluster.news_item_ids == [report.id]
    assert cluster.news_first_seen_at == report.first_seen_at


def test_bots_and_feed_accounts_do_not_make_buzz(db_session: Session) -> None:
    for n in range(20):  # a feed account posting the article with everything else it posts
        post(
            db_session,
            "mastodon",
            100 + n,
            when=NOW - timedelta(hours=1),
            author="techwire",
            link=ARTICLE if n == 0 else f"https://x.example/{n}",
        )
    post(db_session, "bluesky", 2, when=NOW - timedelta(minutes=30), link=ARTICLE)
    post(db_session, "hn", 3, when=NOW - timedelta(minutes=20), link=ARTICLE)

    run(db_session, now=NOW, heat=FixedHeat(5.0))

    (cluster,) = live(db_session)
    assert (cluster.post_count, cluster.human_posts, cluster.author_count) == (3, 2, 2)
    assert cluster.crossed_at is None and not cluster.breaking


def test_one_platform_needs_more_people_and_heat(db_session: Session) -> None:
    for n in range(4):
        post(db_session, "threads", n, when=NOW - timedelta(minutes=30), link=ARTICLE)
    run(db_session, now=NOW, heat=FixedHeat(2.0))
    (cluster,) = live(db_session)
    assert cluster.crossed_at is None  # four people, one platform

    post(db_session, "threads", 9, when=NOW - timedelta(minutes=10), link=ARTICLE)
    run(db_session, now=NOW + timedelta(minutes=10), heat=FixedHeat(2.0))
    (cluster,) = live(db_session)
    assert cluster.crossed_at is not None and cluster.platforms == ["threads"]


def test_old_stories_cross_but_are_not_breaking(db_session: Session) -> None:
    three_platforms(db_session, NOW - timedelta(hours=7))

    run(db_session, now=NOW, heat=FixedHeat(0.6))

    (cluster,) = live(db_session)
    assert cluster.crossed_at == NOW and not cluster.breaking


def test_clusters_keep_their_id_and_merge_into_the_larger(db_session: Session) -> None:
    other = "https://example.org/other-article"
    first = post(db_session, "mastodon", 1, when=NOW - timedelta(minutes=40), link=ARTICLE)
    post(db_session, "bluesky", 2, when=NOW - timedelta(minutes=35), link=ARTICLE)
    post(db_session, "hn", 3, when=NOW - timedelta(minutes=31), link=ARTICLE)
    post(db_session, "mastodon", 10, when=NOW - timedelta(minutes=30), link=other)
    post(db_session, "bluesky", 11, when=NOW - timedelta(minutes=30), link=other)
    run(db_session, now=NOW, heat=FixedHeat(0.6))
    story, side = live(db_session)
    assert story.breaking and side.crossed_at is None and side.post_count == 2

    bridge = post(db_session, "hn", 12, when=NOW + timedelta(minutes=5), link=other)
    run(db_session, now=NOW + timedelta(minutes=10), heat=FixedHeat(0.6))
    assert db_session.get(BuzzClusterItem, bridge.id).cluster_id == side.id  # type: ignore[union-attr]
    # the bridge turns out to share the first article too (both links in one post)
    keys, article = (db_session.get(BuzzItemKeys, i) for i in (bridge.id, first.id))
    assert keys is not None and article is not None
    keys.links = sorted({*keys.links, *article.links})
    db_session.flush()
    run(db_session, now=NOW + timedelta(minutes=20), heat=FixedHeat(0.6))

    (cluster,) = live(db_session)
    assert cluster.id == story.id and cluster.post_count == 6
    assert cluster.breaking and cluster.breaking_at == NOW and cluster.crossed_at == NOW
    assert db_session.get(BuzzCluster, side.id).merged_into == story.id  # type: ignore[union-attr]
    assert not db_session.scalars(
        select(BuzzClusterItem).where(BuzzClusterItem.cluster_id == side.id)
    ).all()


def test_repeats_across_instances_count_once(db_session: Session) -> None:
    # the same toot seen on two instances is stored as a repeat (content/duplicates.py)
    post(db_session, "mastodon", 1, when=NOW - timedelta(minutes=40), title="Same toot text here x")
    post(db_session, "bluesky", 2, when=NOW - timedelta(minutes=35), link=ARTICLE)
    run(db_session, now=NOW, heat=FixedHeat(1.0))
    assert live(db_session) == []
