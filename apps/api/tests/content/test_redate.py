from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.models import Item
from news_insight.content.redate import apply_redate, page_date, plan_page_dates, plan_redate
from news_insight.sources.enums import AccessMethod, Region
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 27, 0, 0, tzinfo=UTC)
NINE = timedelta(hours=9)


def stored(
    session: Session, source: Source, n: int, published: datetime | None, **kw: object
) -> Item:
    item = Item(
        source_id=source.id,
        track=source.track,
        stable_id=f"id-{n}",
        url=f"https://www.example.com/{n}",
        canonical_url=f"https://www.example.com/{n}",
        title=f"t{n}",
        content_hash=f"h{n}",
        published_at=published,
        first_seen_at=kw.pop("seen", NOW - timedelta(hours=n)),  # type: ignore[arg-type]
        last_changed_at=NOW,
        **kw,
    )
    session.add(item)
    session.flush()
    return item


def test_a_zoneless_feed_moves_every_item_by_the_offset_its_fresh_entries_show(
    db_session: Session,
) -> None:
    source = build_source(region=Region.KR, access_method=AccessMethod.FEED)
    db_session.add(source)
    db_session.flush()
    # true times, and what the old reading stored: nine hours later
    truth = {n: NOW - timedelta(hours=n, minutes=30) for n in range(1, 6)}
    for n, moment in truth.items():
        stored(db_session, source, n, moment + NINE)
    in_feed = [
        RawItem(
            stable_id=f"id-{n}",
            url=f"https://www.example.com/{n}",
            title="t",
            published_at=truth[n],
        )
        for n in (1, 2, 3)
    ]

    plan = plan_redate(
        db_session, since=NOW - timedelta(days=3), now=NOW, feeds=lambda _source, _now: in_feed
    )

    [repair] = plan.sources
    assert (repair.matched, repair.shift, repair.changed) == (3, NINE, 5)
    apply_redate(db_session, plan)
    dates = dict(db_session.execute(select(Item.stable_id, Item.published_at)).tuples().all())
    assert dates == {f"id-{n}": moment for n, moment in truth.items()}


def test_without_a_feed_only_impossible_dates_change(db_session: Session) -> None:
    source = build_source(region=Region.KR, access_method=AccessMethod.SITEMAP)
    db_session.add(source)
    db_session.flush()
    stored(db_session, source, 1, NOW - timedelta(days=1))  # fine
    stored(db_session, source, 2, NOW + timedelta(hours=7), seen=NOW)  # wall clock read as UTC
    stored(db_session, source, 3, NOW + timedelta(days=9), seen=NOW)  # cannot be right
    stored(db_session, source, 4, None, body="입력 2026.10.26 18:00 본문", seen=NOW)

    plan = plan_redate(db_session, since=NOW - timedelta(days=3), now=NOW, feeds=None)

    by_id = {
        db_session.get(Item, item_id).stable_id: date  # type: ignore[union-attr]
        for item_id, date in plan.changes.items()
    }
    assert by_id == {
        "id-2": NOW - timedelta(hours=2),
        "id-3": None,
        "id-4": datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
    }


def test_a_later_edited_date_in_the_feed_does_not_replace_the_first(db_session: Session) -> None:
    source = build_source(access_method=AccessMethod.FEED)
    db_session.add(source)
    db_session.flush()
    first = NOW - timedelta(hours=3)
    stored(db_session, source, 1, first, seen=NOW - timedelta(hours=2))
    edited = [
        RawItem(stable_id="id-1", url="https://www.example.com/1", title="t", published_at=NOW)
    ]

    plan = plan_redate(
        db_session, since=NOW - timedelta(days=3), now=NOW, feeds=lambda _s, _n: edited
    )

    assert plan.changes == {}


def test_a_feed_holding_fixed_and_misread_entries_still_shows_its_offset(
    db_session: Session,
) -> None:
    source = build_source(region=Region.KR, access_method=AccessMethod.FEED)
    db_session.add(source)
    db_session.flush()
    truth = {n: NOW - timedelta(hours=n, minutes=30) for n in range(1, 9)}
    fixed_at = NOW - timedelta(hours=3)
    for n, moment in truth.items():  # items 1-2 were stored after the fix, the rest before
        stored(db_session, source, n, moment if n <= 2 else moment + NINE)
    in_feed = [
        RawItem(
            stable_id=f"id-{n}",
            url=f"https://www.example.com/{n}",
            title="t",
            published_at=truth[n],
        )
        for n in (1, 2, 3, 4, 5)
    ]

    plan = plan_redate(
        db_session,
        since=NOW - timedelta(days=3),
        now=NOW,
        feeds=lambda _s, _n: in_feed,
        shift_before=fixed_at,
    )

    assert plan.sources[0].shift == NINE
    apply_redate(db_session, plan)
    dates = dict(db_session.execute(select(Item.stable_id, Item.published_at)).tuples().all())
    assert dates == {f"id-{n}": moment for n, moment in truth.items()}


def test_an_offset_other_than_the_source_zone_is_not_applied(db_session: Session) -> None:
    source = build_source(region=Region.KR, access_method=AccessMethod.FEED)
    db_session.add(source)
    db_session.flush()
    for n in range(1, 5):
        stored(db_session, source, n, NOW - timedelta(hours=n + 3))
    in_feed = [
        RawItem(
            stable_id=f"id-{n}",
            url=f"https://www.example.com/{n}",
            title="t",
            published_at=NOW - timedelta(hours=n + 5),
        )
        for n in range(1, 4)
    ]

    plan = plan_redate(
        db_session, since=NOW - timedelta(days=3), now=NOW, feeds=lambda _s, _n: in_feed
    )

    assert plan.sources[0].shift is None


def test_page_dates_replace_a_lastmod_but_never_move_a_date_forward(db_session: Session) -> None:
    sitemap = build_source(key="corp", access_method=AccessMethod.SITEMAP)
    db_session.add(sitemap)
    db_session.flush()
    edited = stored(db_session, sitemap, 1, NOW - timedelta(hours=2))  # lastmod of a 2024 post
    relabelled = stored(db_session, sitemap, 2, NOW - timedelta(hours=12))
    contradicts = stored(db_session, sitemap, 3, NOW - timedelta(hours=5))
    blocked = stored(db_session, sitemap, 4, NOW - timedelta(hours=6))
    pages = {
        edited.url: [datetime(2024, 5, 2, 15, tzinfo=UTC)],
        relabelled.url: [NOW - timedelta(hours=3)],  # local time marked Z: later, ignored
        contradicts.url: [NOW - timedelta(days=3), NOW - timedelta(days=2)],
    }

    plan = plan_page_dates(
        db_session, sources=["corp"], pages=lambda url, tz: pages.get(url), workers=2
    )

    assert plan.changes == {edited.id: datetime(2024, 5, 2, 15, tzinfo=UTC)}
    assert blocked.id not in plan.changes
    apply_redate(db_session, plan)
    assert edited.published_at == datetime(2024, 5, 2, 15, tzinfo=UTC)


def test_a_feed_takes_the_page_only_when_it_is_the_zone_offset_earlier() -> None:
    from zoneinfo import ZoneInfo

    seoul, seen = ZoneInfo("Asia/Seoul"), NOW
    read_as_utc = datetime(2026, 10, 2, 17, 35, tzinfo=UTC)  # 17:35 KST read as UTC
    truth = read_as_utc - NINE

    assert page_date(read_as_utc, [truth], seen=seen, tz=seoul, offset_only=True) == truth
    # a page 3 h earlier is some other date (its update, a mislabel): not taken from a feed
    other = read_as_utc - timedelta(hours=3)
    assert page_date(read_as_utc, [other], seen=seen, tz=seoul, offset_only=True) is None
    assert page_date(read_as_utc, [other], seen=seen, tz=seoul, offset_only=False) == other
