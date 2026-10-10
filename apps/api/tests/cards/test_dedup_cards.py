"""Duplicate removal before carding (2026-10-10): repeats never reach an engine."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemTriage
from news_insight.cards.service import REUSED, CardPolicy, pending_count, pending_items, run_cards
from news_insight.collect.contracts import RawItem
from news_insight.content.duplicates import backfill
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item, ItemDedup
from news_insight.sources.enums import AccessMethod, SourceStatus, StorageRight
from news_insight.sources.models import Source
from tests.cards.test_service import FULL, FakeAgy, cards, scope_for
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 4, 3, tzinfo=UTC)
POLICY = CardPolicy(agy_batch=10, agy_parallel=1, time_budget_seconds=1000)
TITLE = "Pentagon stops using Anthropic AI tools after blacklisting company"
BODY = "The US Department of Defense has stopped using the tools of the AI company Anthropic."


def source(db_session: Session, key: str, **kwargs: Any) -> Source:
    row = build_source(key=key, storage_right=StorageRight.EXCERPT_ALLOWED, **kwargs)
    db_session.add(row)
    db_session.flush()
    return row


def ingest(db_session: Session, src: Source, raws: list[RawItem]) -> None:
    ingest_items(db_session, src, raws, fetch_run=None, now=NOW, canary=True)


def dedup(db_session: Session, title: str) -> ItemDedup:
    item = db_session.scalars(select(Item).where(Item.title == title)).one()
    return db_session.get(ItemDedup, item.id)


def test_repeats_are_assigned_at_ingest_and_skip_the_queue(db_session: Session) -> None:
    news = source(db_session, "bbc")
    mirror = source(db_session, "mirror")
    tags = [
        source(db_session, f"masto-{tag}", access_method=AccessMethod.ACTIVITYPUB)
        for tag in ("ai", "tech")
    ]
    ingest(
        db_session,
        news,
        [RawItem(stable_id="a", url="https://www.bbc.co.uk/n/1", title=TITLE, summary=BODY)],
    )
    ingest(
        db_session,
        mirror,
        [
            RawItem(
                stable_id="b",
                url="https://bbc.co.uk/n/1?at_campaign=rss",
                title="Pentagon (mirror)",
                summary="x",
            )
        ],
    )
    for tag in tags:  # the same post in two hashtag feeds, sharing the article
        ingest(
            db_session,
            tag,
            [
                RawItem(
                    stable_id="p",
                    url="https://mastodon.social/@x/9",
                    title="Big news",
                    summary="<p>Big news</p>",
                    link="https://www.bbc.co.uk/n/1",
                )
            ],
        )
    root = db_session.scalars(select(Item).where(Item.title == TITLE)).one()
    assert dedup(db_session, "Pentagon (mirror)").matched_by == "url"
    posts = db_session.scalars(
        select(ItemDedup).join(Item, Item.id == ItemDedup.item_id).where(Item.title == "Big news")
    ).all()
    assert [p.duplicate_of for p in posts] == [root.id, root.id]
    assert {p.matched_by for p in posts} == {"link", "url"}
    assert pending_count(db_session) == 1  # one story, one engine input

    agy = FakeAgy([FULL])
    stats = run_cards(scope_for(db_session), agy=agy, qwen=None, policy=POLICY)

    assert agy.batches == [[root.id]] and stats.ready == 1 and stats.reused == 3
    made = cards(db_session)
    assert made["Big news"].engine == REUSED and made["Big news"].title_ko == f"[agy] {TITLE}"
    assert pending_count(db_session) == 0


def test_a_root_that_can_never_be_carded_does_not_hold_repeats(db_session: Session) -> None:
    held = source(db_session, "held", status=SourceStatus.PAUSED)
    live = source(db_session, "live")
    ingest(
        db_session,
        held,
        [RawItem(stable_id="a", url="https://ex.com/1", title=TITLE, summary=BODY)],
    )
    ingest(
        db_session,
        live,
        [RawItem(stable_id="b", url="https://ex.com/1", title="copy", summary=BODY)],
    )
    assert dedup(db_session, "copy").matched_by == "url"
    assert [item.title for item, _ in pending_items(db_session, limit=10)] == ["copy"]


def test_title_rule_keeps_different_reports_apart(db_session: Session) -> None:
    src = source(db_session, "apps")
    title = "PUBG MOBILE | US | Darkpool Chart Explorer ranking"
    ingest(
        db_session,
        src,
        [
            RawItem(
                stable_id="a",
                url="https://ex.com/android",
                title=title,
                summary="PUBG MOBILE on Android in US: Top Free Games ranking history and movement",
            ),
            RawItem(
                stable_id="b",
                url="https://ex.com/ios",
                title=title + " ",
                summary="PUBG MOBILE on iOS in US: Top Free Games ranking history and movement",
            ),
        ],
    )
    rows = db_session.scalars(select(ItemDedup)).all()
    assert [r.duplicate_of for r in rows] == [None, None]


def test_cap_bypass_passes_items_with_a_good_triage_probability(db_session: Session) -> None:
    src = source(db_session, "candidate-feed")
    ingest(
        db_session,
        src,
        [
            RawItem(stable_id=s, url=f"https://ex.com/{s}", title=f"{s} item", summary="본문")
            for s in ("x", "y", "z")
        ],
    )
    run_cards(
        scope_for(db_session),
        agy=FakeAgy([FULL]),
        qwen=None,
        policy=CardPolicy(
            agy_batch=2, agy_parallel=1, unvalidated_daily_cap=2, time_budget_seconds=1000
        ),
    )
    carded = set(cards(db_session))
    (left,) = [i for i in db_session.scalars(select(Item)) if i.title not in carded]
    assert pending_items(db_session, limit=10, unvalidated_daily_cap=2) == []
    db_session.add(
        ItemTriage(
            item_id=left.id,
            dx_probability=0.6,
            weight=1.0,
            score=0.6,
            themes=[],
            matched=[],
            scored_at=NOW,
        )
    )
    db_session.flush()
    assert pending_items(db_session, limit=10, unvalidated_daily_cap=2, cap_bypass_dx=0.8) == []
    assert len(pending_items(db_session, limit=10, unvalidated_daily_cap=2)) == 1  # 0.5 default


def test_backfill_keys_old_items_and_recovers_split_mastodon_links(db_session: Session) -> None:
    news = source(db_session, "digitimes")
    social = source(db_session, "masto", access_method=AccessMethod.ACTIVITYPUB)
    ingest(
        db_session,
        news,
        [
            RawItem(
                stable_id="a",
                url="https://www.digitimes.com/news/a20261008VL223/jntc-glass.htm",
                title="JNTC to invest in glass substrates",
                summary=BODY,
            )
        ],
    )
    ingest(
        db_session,
        social,
        [
            RawItem(
                stable_id="p",
                url="https://mastodon.social/@s/1",
                title="JNTC plans to invest",
                summary=(
                    "JNTC plans to invest about US$259 million. Source: DigiTimes Asia "
                    "https://www. digitimes.com/news/a20261008VL 223/jntc-glass.htm"
                ),
            )
        ],
    )
    db_session.query(ItemDedup).delete()  # as before item_dedup existed
    db_session.flush()

    stats = backfill(db_session, now=NOW)

    assert stats.keyed == 2 and stats.links == 1 and stats.by_kind == {"link": 1}
    post = dedup(db_session, "JNTC plans to invest")
    assert post.matched_by == "link" and post.duplicate_of is not None
    assert (
        db_session.scalars(select(Item.title).where(Item.id == post.duplicate_of)).one()
        == "JNTC to invest in glass substrates"
    )
    assert cards(db_session) == {}  # backfill writes no cards
