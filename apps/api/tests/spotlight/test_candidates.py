import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item, ItemDedup, ItemMetricSnapshot
from news_insight.sources.enums import Region, Track, ValidationStage
from news_insight.sources.models import Source
from news_insight.spotlight import candidates as candidates_module
from news_insight.spotlight.candidates import (
    INTERVIEW_PATTERN,
    SECTIONS,
    collect_candidates,
    window,
)
from news_insight.stories.models import ItemRef, Relation, Story, StoryItem
from tests.factories import build_source

pytestmark = pytest.mark.db
DAY = date(2026, 11, 4)
START, END = window(DAY)
SEEN = END - timedelta(hours=10)
NOW = END


CATEGORY = {
    Track.COMMUNITY: "dev_forum",
    Track.OSS: "github_trending",
    Track.RESEARCH_IP: "academic_paper",
}


def source(
    session: Session,
    key: str,
    track: Track,
    operator: str | None = None,
    category: str | None = None,
) -> Source:
    row = session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if row is None:
        row = build_source(
            key=key,
            name=key,
            operator=operator or f"{key} Inc.",
            track=track,
            category=category or CATEGORY.get(track, "independent_media"),
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
    title: str | None = None,
) -> Item:
    url = f"https://{src.key}.com/{slug}"
    ingest_items(
        session,
        src,
        [
            RawItem(
                stable_id=url,
                url=url,
                title=title or f"{slug} headline",
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


def test_link_sharing_post_is_community_candidate(db_session: Session):
    article = news_story(db_session, "shared", 2)
    posts = hn_posts(db_session, [5] * 10 + [400])
    viral, other = posts[-1], posts[0]
    article_id = article.representative_item_id
    key = db_session.get(ItemDedup, article_id)
    assert key is not None
    # a post sharing a known article is stored as a repeat of it, matched by its link
    db_session.execute(
        update(ItemDedup)
        .where(ItemDedup.item_id == viral.id)
        .values(link_key=key.url_key, duplicate_of=article_id, matched_by="link")
    )
    # any other kind of repeat stays out
    db_session.execute(
        update(ItemDedup)
        .where(ItemDedup.item_id == other.id)
        .values(duplicate_of=posts[1].id, matched_by="title")
    )
    db_session.flush()
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.item_ids for c in result["community"]] == [[viral.id]]
    # it still counts as a mention of the article's event
    assert result["news"][0].metrics["community_mentions"] == 1


def test_rows_do_not_load_body_or_summary(db_session: Session):
    news_story(db_session, "light", 2)
    db_session.flush()
    db_session.expunge_all()
    rows = candidates_module._eligible_items(db_session, START, END)
    assert rows
    unloaded = inspect(rows[0].item).unloaded
    assert {"body", "summary", "canonical_url"} <= unloaded
    assert "title" not in unloaded


def test_only_rows_a_section_needs_are_scored(db_session: Session, monkeypatch):
    news_story(db_session, "plain", 3)
    hn_posts(db_session, [5, 6])
    scored: list[Track] = []
    original = candidates_module.Scorer.add

    def spy(self, rows):
        scored.extend(row.item.track for row in rows)
        return original(self, rows)

    monkeypatch.setattr(candidates_module.Scorer, "add", spy)
    collect_candidates(db_session, day=DAY, now=NOW)
    assert scored
    assert Track.NEWS not in scored


def card(session: Session, target: Item, signal: str | None) -> ItemCard:
    row = ItemCard(
        item_id=target.id,
        status=CardStatus.READY,
        title_ko=f"카드 {target.id}",
        summary_ko=["요약"],
        keywords=[],
        signal_type=signal,
        engine="agy",
        model="m",
        input_hash="h",
        attempts=0,
        generated_at=SEEN,
    )
    session.add(row)
    session.flush()
    return row


def launch_story(session: Session, name: str, count: int = 2, signal: str = "launch") -> Story:
    row = news_story(session, name, count)
    card(session, session.get(Item, row.representative_item_id), signal)  # type: ignore[arg-type]
    return row


def share(session: Session, post: Item, target: Item) -> None:
    """`post` shares `target`'s article (as ingest stores it: a link repeat of that item)."""
    key = session.get(ItemDedup, target.id)
    assert key is not None
    session.execute(
        update(ItemDedup)
        .where(ItemDedup.item_id == post.id)
        .values(link_key=key.url_key, duplicate_of=target.id, matched_by="link")
    )
    session.flush()


def ref(session: Session, target: Item, kind: str, value: str) -> None:
    session.add(ItemRef(item_id=target.id, kind=kind, value=value, meta={}))
    session.flush()


def test_product_limit_is_forty(db_session: Session):
    for n in range(45):
        launch_story(db_session, f"launch{n}")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["product"]) == 40
    assert result["product"][0].cid == "p1"
    assert result["product"][-1].cid == "p40"


def test_product_only_launch_cards_with_two_sources_or_community_z(db_session: Session):
    big = launch_story(db_session, "big", 4)
    pair = launch_story(db_session, "pair", 2)
    launch_story(db_session, "other", 3, signal="research")
    # a lone launch item: one source, nobody talks about it
    lone = item(db_session, source(db_session, "lone", Track.NEWS), "lone")
    card(db_session, lone, "launch")
    # a lone launch item that a viral post shares
    hot = item(db_session, source(db_session, "hot", Track.NEWS), "hot")
    card(db_session, hot, "launch")
    posts = hn_posts(db_session, [5] * 10 + [400])
    share(db_session, posts[-1], hot)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    keys = [c.key for c in result["product"]]
    assert keys[:2] == [f"story:{big.id}", f"story:{pair.id}"]
    assert keys[2] == f"item:{hot.id}"
    assert f"item:{lone.id}" not in keys
    assert len(keys) == 3
    top = result["product"][0]
    assert top.score == pytest.approx(400.0)
    assert top.metrics == {"source_count": 4, "community_mentions": 0, "community_z": 0.0}
    assert top.title_ko == f"카드 {big.representative_item_id}"
    hot_candidate = result["product"][2]
    assert 101.0 < hot_candidate.score < 110.0  # one source (100) plus the post's z
    assert hot_candidate.metrics["community_mentions"] == 1


def test_oss_mentions_raise_rank(db_session: Session):
    gh = source(db_session, "gh", Track.OSS, "GitHub")
    quiet = item(db_session, gh, "quiet", metrics={"trending_stars_daily": 500})
    loud = item(db_session, gh, "loud", metrics={"trending_stars_daily": 500})
    for n in range(32):
        item(db_session, gh, f"filler{n}", metrics={"trending_stars_daily": 5})
    ref(db_session, quiet, "github", "acme/quiet")
    ref(db_session, loud, "github", "acme/loud")
    posts = hn_posts(db_session, [5, 5, 5])
    for post in posts:
        ref(db_session, post, "github", "acme/loud")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.item_ids for c in result["oss"]] == [[loud.id], [quiet.id]]
    first, second = result["oss"]
    assert first.metrics["mentions"] == 3
    assert second.metrics["mentions"] == 0
    assert first.metrics["trending_stars_daily"] == 500
    assert first.score - second.score == pytest.approx(1.5)
    assert first.cid == "o1"


def test_oss_floor_is_z_or_two_mentions(db_session: Session):
    gh = source(db_session, "gh", Track.OSS, "GitHub")
    for n in range(32):
        item(db_session, gh, f"filler{n}", metrics={"trending_stars_daily": 5})
    spike = item(db_session, gh, "spike", metrics={"trending_stars_daily": 500})
    one = item(db_session, gh, "one", metrics={"trending_stars_daily": 5})
    two = item(db_session, gh, "two", metrics={"trending_stars_daily": 5})
    bare = item(db_session, gh, "bare")  # no metrics: no z, but two mentions are enough
    ref(db_session, one, "github", "acme/one")
    ref(db_session, two, "github", "acme/two")
    ref(db_session, bare, "hf", "acme/bare")
    posts = hn_posts(db_session, [5, 5, 5, 5, 5])
    ref(db_session, posts[0], "github", "acme/one")
    for post in posts[1:3]:
        ref(db_session, post, "github", "acme/two")
    for post in posts[3:]:
        ref(db_session, post, "hf", "acme/bare")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert {c.item_ids[0] for c in result["oss"]} == {spike.id, two.id, bare.id}
    assert one.id not in {c.item_ids[0] for c in result["oss"]}


def test_oss_mention_ignores_the_item_itself_and_repeats(db_session: Session):
    gh = source(db_session, "gh", Track.OSS, "GitHub")
    target = item(db_session, gh, "target", metrics={"trending_stars_daily": 5})
    ref(db_session, target, "github", "acme/target")
    posts = hn_posts(db_session, [5, 5, 5])
    for post in posts:
        ref(db_session, post, "github", "acme/target")
    # a url repeat and a post outside the window do not count; a link-sharing post does
    db_session.execute(
        update(ItemDedup)
        .where(ItemDedup.item_id == posts[0].id)
        .values(duplicate_of=posts[1].id, matched_by="url")
    )
    old = item(
        db_session, source(db_session, "hn", Track.COMMUNITY, HN), "old", seen=START - timedelta(1)
    )
    ref(db_session, old, "github", "acme/target")
    share(db_session, posts[2], target)
    db_session.flush()
    result = collect_candidates(db_session, day=DAY, now=NOW)
    # posts[1] and posts[2] count: two mentions, enough for the floor
    assert [c.metrics["mentions"] for c in result["oss"]] == [2]


def test_interview_includes_video_and_title_pattern(db_session: Session):
    yt = source(
        db_session,
        "yt",
        Track.COMMUNITY,
        "Google LLC (YouTube Data API)",
        category="video_channel",
    )
    video = item(db_session, yt, "talk", metrics={"views": 12000})
    news = source(db_session, "wire", Track.NEWS)
    ceo = item(db_session, news, "ceo", title="Nvidia CEO interview on the next chip")
    item(db_session, news, "plain", title="Chip maker posts earnings")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert {c.item_ids[0] for c in result["interview"]} == {video.id, ceo.id}
    assert all(c.cid.startswith("i") for c in result["interview"])


def test_interview_podcast_category_and_korean_pattern(db_session: Session):
    pod = source(db_session, "pod", Track.NEWS, category="podcast_newsletter")
    episode = item(db_session, pod, "ep1", title="Weekly notes")
    wire = source(db_session, "wire", Track.NEWS)
    korean = item(db_session, wire, "kr", title="삼성전자 사장 인터뷰")
    item(db_session, wire, "no", title="Casey interviewed nobody")  # not the word itself
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert {c.item_ids[0] for c in result["interview"]} == {episode.id, korean.id}


def test_interview_score_adds_reports_and_video_views_z(db_session: Session):
    yt = source(
        db_session,
        "yt",
        Track.COMMUNITY,
        "Google LLC (YouTube Data API)",
        category="video_channel",
    )
    for n in range(32):
        item(db_session, yt, f"f{n}", metrics={"views": 10})
    hit = item(db_session, yt, "hit", metrics={"views": 90000})
    wire = [item(db_session, source(db_session, f"w{n}", Track.NEWS), f"w{n}") for n in range(3)]
    covered = item(
        db_session,
        source(db_session, "talk", Track.NEWS),
        "talk",
        title="Founder keynote highlights",
    )
    story(db_session, [covered, *wire], source_count=4)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    by_id = {c.item_ids[0]: c for c in result["interview"]}
    # the story folds to one entry: the covered keynote with its 4 sources
    assert by_id[covered.id].score == pytest.approx(4.0)
    assert by_id[covered.id].key.startswith("story:")
    assert by_id[covered.id].item_ids == [covered.id]
    assert by_id[hit.id].score > 1.0  # views z, no reports
    assert result["interview"][0].item_ids == [hit.id]


def test_interview_has_no_floor_but_caps_at_thirty(db_session: Session):
    wire = source(db_session, "wire", Track.NEWS)
    for n in range(35):
        item(db_session, wire, f"q{n}", title=f"Founder podcast {n}")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["interview"]) == 30


def paper(session: Session, slug: str, *, operator: str | None = None, metrics=None) -> Item:
    src = source(session, f"paper-{slug}", Track.RESEARCH_IP, operator)
    return item(session, src, slug, metrics=metrics)


def test_research_counts_arxiv_mentions(db_session: Session):
    target = paper(db_session, "p1")
    ref(db_session, target, "arxiv", "2610.00001")
    posts = hn_posts(db_session, [5, 5])
    for post in posts:
        ref(db_session, post, "arxiv", "2610.00001")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.item_ids for c in result["research"]] == [[target.id]]
    candidate = result["research"][0]
    assert candidate.metrics["mentions"] == 2
    assert candidate.metrics["upvotes"] == 0
    assert candidate.score == pytest.approx(20.0)
    assert candidate.cid == "r1"


def test_research_without_mentions_or_upvotes_excluded(db_session: Session):
    paper(db_session, "silent")
    ref_only = paper(db_session, "ref-only")
    ref(db_session, ref_only, "doi", "10.1000/abc")
    paper(db_session, "few", operator="Hugging Face Daily Papers", metrics={"upvotes": 9})
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert result["research"] == []


def test_research_hf_upvotes_floor_and_z(db_session: Session):
    op = "Hugging Face Daily Papers"
    for n in range(32):
        paper(db_session, f"low{n}", operator=op, metrics={"upvotes": 1, "comments": 0})
    ten = paper(db_session, "ten", operator=op, metrics={"upvotes": 10, "comments": 0})
    top = paper(db_session, "top", operator=op, metrics={"upvotes": 300, "comments": 20})
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.item_ids[0] for c in result["research"]] == [top.id, ten.id]
    assert result["research"][0].metrics["upvotes"] == 300
    assert result["research"][0].score > result["research"][1].score > 0


def test_research_mentions_come_from_news_and_community_only(db_session: Session):
    target = paper(db_session, "p1")
    ref(db_session, target, "doi", "10.1000/xyz")
    news = item(db_session, source(db_session, "wire", Track.NEWS), "about")
    ref(db_session, news, "doi", "10.1000/xyz")
    ref(db_session, news, "arxiv", "2610.00009")  # unrelated second ref
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert result["research"][0].metrics["mentions"] == 1


def test_patent_ip_story_included(db_session: Session):
    ip = launch_story(db_session, "ip", 3, signal="ip")
    launch_story(db_session, "plain", 3, signal="launch")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert [c.key for c in result["patent"]] == [f"story:{ip.id}"]
    assert result["patent"][0].cid == "t1"
    assert result["patent"][0].score == pytest.approx(3.0)


def test_patent_office_item_needs_a_mention(db_session: Session):
    office = source(db_session, "epo", Track.RESEARCH_IP, category="patent_office")
    silent = item(db_session, office, "silent")
    talked = item(db_session, office, "talked")
    posts = hn_posts(db_session, [5])
    share(db_session, posts[0], talked)
    ip = launch_story(db_session, "ip", 2, signal="ip")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    by_key = {c.key: c for c in result["patent"]}
    assert set(by_key) == {f"item:{talked.id}", f"story:{ip.id}"}
    assert f"item:{silent.id}" not in by_key
    # one report (itself) plus one mention vs two reports
    assert by_key[f"item:{talked.id}"].score == pytest.approx(2.0)
    assert by_key[f"item:{talked.id}"].metrics["mentions"] == 1
    assert by_key[f"story:{ip.id}"].score == pytest.approx(2.0)


@pytest.mark.parametrize(
    "title",
    [
        "Energy sector outlook",
        "Director named",
        "Doctor visits rise at the factory",
        "Fed official says rates",
        "Ceo-less startup raises funds",
        "Interviewing the interns",
    ],
)
def test_interview_pattern_rejects_ordinary_headlines(title: str):
    assert INTERVIEW_PATTERN.search(title) is None


@pytest.mark.parametrize(
    "title",
    [
        "CEO interview",
        "Keynote at CES",
        "삼성 대표 인터뷰",
        "Acme CTO on agents",
        "Fireside chat with Jensen",
        "Podcast: chips",
        "AMA and Q&A session",
        "기조연설 요약",
        "AI 대담",
    ],
)
def test_interview_pattern_matches_interviews(title: str):
    assert INTERVIEW_PATTERN.search(title) is not None


def test_research_twins_fold_into_one_candidate(db_session: Session):
    arxiv = paper(db_session, "arx")
    hf = paper(db_session, "hf", operator="Hugging Face Daily Papers", metrics={"upvotes": 40})
    ref(db_session, arxiv, "arxiv", "2610.00007")
    ref(db_session, hf, "arxiv", "2610.00007")
    posts = hn_posts(db_session, [5])
    ref(db_session, posts[0], "arxiv", "2610.00007")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["research"]) == 1
    candidate = result["research"][0]
    assert set(candidate.item_ids) == {arxiv.id, hf.id}
    assert candidate.metrics["mentions"] == 1  # the twin is not a mention
    assert candidate.metrics["upvotes"] == 40
    assert candidate.score == pytest.approx(10.0)  # one mention; z is 0 without a pool


def test_research_twins_without_outside_mentions_or_upvotes_are_dropped(db_session: Session):
    arxiv = paper(db_session, "arx")
    hf = paper(db_session, "hf", operator="Hugging Face Daily Papers", metrics={"upvotes": 9})
    ref(db_session, arxiv, "arxiv", "2610.00008")
    ref(db_session, hf, "arxiv", "2610.00008")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert result["research"] == []


def test_research_fold_chains_through_shared_refs_and_keeps_best_lead(db_session: Session):
    a = paper(db_session, "a")
    b = paper(db_session, "b")
    c = paper(db_session, "c")
    ref(db_session, a, "doi", "10.1000/one")
    ref(db_session, b, "doi", "10.1000/one")
    ref(db_session, b, "arxiv", "2610.00010")
    ref(db_session, c, "arxiv", "2610.00010")
    other = paper(db_session, "other")
    ref(db_session, other, "arxiv", "2610.99999")
    posts = hn_posts(db_session, [5, 5, 5])
    ref(db_session, posts[0], "doi", "10.1000/one")
    ref(db_session, posts[1], "arxiv", "2610.00010")
    ref(db_session, posts[2], "arxiv", "2610.00010")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["research"]) == 1
    candidate = result["research"][0]
    assert set(candidate.item_ids) == {a.id, b.id, c.id}
    assert candidate.item_ids[0] == b.id  # b alone sees all three posts
    assert candidate.metrics["mentions"] == 3


def test_oss_items_of_one_repo_fold_into_one_candidate(db_session: Session):
    gh = source(db_session, "gh", Track.OSS, "GitHub")
    first = item(db_session, gh, "trend", metrics={"trending_stars_daily": 500})
    second = item(db_session, gh, "release", metrics={"trending_stars_daily": 400})
    for n in range(32):
        item(db_session, gh, f"filler{n}", metrics={"trending_stars_daily": 5})
    ref(db_session, first, "github", "acme/tool")
    ref(db_session, second, "github", "acme/tool")
    posts = hn_posts(db_session, [5])
    ref(db_session, posts[0], "github", "acme/tool")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert len(result["oss"]) == 1
    candidate = result["oss"][0]
    assert candidate.item_ids == [first.id, second.id]  # the stronger one leads
    assert candidate.metrics["mentions"] == 1
    assert candidate.metrics["trending_stars_daily"] == 500


def test_oss_twin_does_not_count_as_a_mention(db_session: Session):
    gh = source(db_session, "gh", Track.OSS, "GitHub")
    first = item(db_session, gh, "trend", metrics={"trending_stars_daily": 5})
    second = item(db_session, gh, "release", metrics={"trending_stars_daily": 5})
    ref(db_session, first, "github", "acme/tool")
    ref(db_session, second, "github", "acme/tool")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert result["oss"] == []


def snapshot(session: Session, target: Item, at: datetime, **metrics: int) -> None:
    session.add(ItemMetricSnapshot(item_id=target.id, captured_at=at, metrics=metrics))
    session.flush()


DAILY = "github-trending-repositories-daily"
WEEKLY = "github-trending-repositories-weekly"
HF_MODELS = "hf-models-trending"


def test_oss_includes_a_repo_first_seen_earlier_that_trends_again(db_session: Session):
    daily = source(db_session, DAILY, Track.OSS, "GitHub")
    back = item(db_session, daily, "back", seen=SEEN - timedelta(days=3), metrics={"rank": 9})
    snapshot(db_session, back, SEEN, rank=2, stars=900)
    # first seen earlier and not shown again in the window: stays out
    gone = item(db_session, daily, "gone", seen=SEEN - timedelta(days=3), metrics={"rank": 1})
    result = collect_candidates(db_session, day=DAY, now=NOW)
    leads = [c.item_ids[0] for c in result["oss"]]
    assert back.id in leads
    assert gone.id not in leads
    (candidate,) = result["oss"]
    assert candidate.metrics["rank"] == 2  # the latest snapshot
    assert candidate.metrics["basis"] == "github_daily"
    assert candidate.metrics["trend_rank"] == 2


def test_oss_backfills_to_ten_from_daily_weekly_then_hf(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(candidates_module, "MIN_OSS_Z", 1e9)  # only mentions lift a repo here
    daily = source(db_session, DAILY, Track.OSS, "GitHub")
    weekly = source(db_session, WEEKLY, Track.OSS, "GitHub")
    hf = source(db_session, HF_MODELS, Track.OSS, "Hugging Face")
    talked = item(db_session, daily, "talked", metrics={"rank": 20})
    ref(db_session, talked, "github", "acme/talked")
    for n in range(2):
        post = item(db_session, source(db_session, f"press{n}", Track.NEWS), f"press{n}")
        ref(db_session, post, "github", "acme/talked")
    days = {
        rank: item(db_session, daily, f"d{rank}", metrics={"rank": rank}) for rank in (4, 1, 3, 2)
    }
    eleventh = item(db_session, daily, "d11", metrics={"rank": 11})
    for rank, row in days.items():
        ref(db_session, row, "github", f"acme/d{rank}")
    weeks = {
        rank: item(db_session, weekly, f"w{rank}", metrics={"rank": rank}) for rank in (1, 2, 3, 4)
    }
    ref(db_session, weeks[1], "github", "acme/d2")  # the same repo as daily #2
    hfs = {t: item(db_session, hf, f"h{t}", metrics={"trending": t}) for t in (20, 50, 30, 40)}
    result = collect_candidates(db_session, day=DAY, now=NOW)
    oss = result["oss"]
    assert len(oss) == 10
    assert [c.item_ids[0] for c in oss] == [
        talked.id,
        days[1].id,
        days[2].id,
        days[3].id,
        days[4].id,
        weeks[2].id,
        weeks[3].id,
        weeks[4].id,
        hfs[50].id,
        hfs[40].id,
    ]
    assert "basis" not in oss[0].metrics
    assert [(c.metrics["basis"], c.metrics["trend_rank"]) for c in oss[1:]] == [
        ("github_daily", 1),
        ("github_daily", 2),
        ("github_daily", 3),
        ("github_daily", 4),
        ("github_weekly", 2),
        ("github_weekly", 3),
        ("github_weekly", 4),
        ("hf_trending", 1),
        ("hf_trending", 2),
    ]
    assert oss[2].item_ids == [days[2].id, weeks[1].id]  # one repo, one candidate
    assert [c.stat_rank for c in oss] == list(range(1, 11))
    assert eleventh.id not in {i for c in oss for i in c.item_ids}
    assert len({c.key for c in oss}) == 10


def ai_card(session: Session, target: Item, signal: str, field: str = "ai") -> ItemCard:
    row = card(session, target, signal)
    row.field = field
    session.flush()
    return row


def test_ai_takes_ai_field_launch_market_and_ecosystem_events(db_session: Session):
    stories = {}
    for name, signal, field in (
        ("model", "launch", "ai"),
        ("deal", "market", "ai"),
        ("hub", "ecosystem", "ai"),
        ("funding", "finance", "ai"),
        ("chip", "launch", "semis"),
    ):
        row = news_story(db_session, name, 3 if name == "model" else 2)
        ai_card(db_session, db_session.get(Item, row.representative_item_id), signal, field)  # type: ignore[arg-type]
        stories[name] = row
    lone = item(db_session, source(db_session, "lone", Track.NEWS), "lone")
    ai_card(db_session, lone, "launch")
    result = collect_candidates(db_session, day=DAY, now=NOW)
    keys = [c.key for c in result["ai"]]
    assert keys[0] == f"story:{stories['model'].id}"
    assert set(keys) == {f"story:{stories[n].id}" for n in ("model", "deal", "hub")}
    top = result["ai"][0]
    assert top.cid == "a1"
    assert top.metrics == {"source_count": 3, "community_mentions": 0, "community_z": 0.0}
    assert top.score == pytest.approx(300.0)
    # the semis launch is a product, not an AI model or service
    assert f"story:{stories['chip'].id}" in {c.key for c in result["product"]}


def test_ai_takes_benchmark_arrivals_and_big_moves(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    changes = {
        "new_models": [
            {"site": "LMArena", "board": "text", "model": "Gemini 3.8 Pro", "rank": 4},
            {
                "site": "LiveBench",
                "board": "overall",
                "model": "gemini-3.8-pro",
                "rank": 2,
                "previous_rank": 25,
            },
        ],
        "changes": [
            {"site": "LMArena", "board": "text", "model": "Claude Opus 5.5", "from": 9, "to": 3},
            {"site": "LMArena", "board": "text", "model": "GPT-6", "from": 5, "to": 3},
            {"site": "LMArena", "board": "text", "model": "Grok 6", "from": 7, "to": 6},
        ],
    }
    monkeypatch.setattr(candidates_module, "benchmark_changes", lambda session, *, now: changes)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    by_key = {c.key: c for c in result["ai"]}
    assert set(by_key) == {"model:gemini-3-8-pro", "model:claude-opus-5-5"}
    gemini = by_key["model:gemini-3-8-pro"]
    assert gemini.title_ko == "gemini-3.8-pro — LiveBench overall 2위"
    assert gemini.metrics == {
        "basis": "benchmark",
        "site": "LiveBench",
        "board": "overall",
        "rank": 2,
        "from": 25,
    }
    assert gemini.score == pytest.approx(98.0)
    assert gemini.item_ids == []
    claude = by_key["model:claude-opus-5-5"]
    assert claude.metrics["from"] == 9
    assert "9위에서 3위로" in claude.summary_ko
    assert [c.key for c in result["ai"]] == ["model:gemini-3-8-pro", "model:claude-opus-5-5"]


def test_ai_survives_unavailable_benchmarks(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    def broken(session: Session, *, now: datetime) -> dict:
        raise RuntimeError("leaderboard tables missing")

    monkeypatch.setattr(candidates_module, "benchmark_changes", broken)
    assert collect_candidates(db_session, day=DAY, now=NOW)["ai"] == []


def test_ai_takes_hot_hugging_face_models_the_oss_section_did_not(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    hf = source(db_session, HF_MODELS, Track.OSS, "Hugging Face")
    hn_posts(db_session, [5] * 32)
    hot = item(db_session, hf, "hot", metrics={"trending": 500})
    calm = item(db_session, hf, "calm", metrics={"trending": 1})
    # an HF model the oss section takes stays there
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert hot.id in {c.item_ids[0] for c in result["oss"]}
    assert result["ai"] == []
    # with the oss section full of others, it is an AI candidate
    monkeypatch.setattr(candidates_module, "MIN_OSS_Z", 1e9)
    monkeypatch.setattr(candidates_module, "MIN_OSS", 0)
    result = collect_candidates(db_session, day=DAY, now=NOW)
    assert result["oss"] == []
    (candidate,) = result["ai"]
    assert candidate.item_ids == [hot.id]
    assert candidate.metrics["basis"] == "hf_trending"
    assert candidate.score > 1.0
    assert calm.id not in candidate.item_ids
