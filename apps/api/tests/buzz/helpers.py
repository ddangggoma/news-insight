from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import RawItem
from news_insight.content.ingest import ingest_items
from news_insight.content.models import Item
from news_insight.sources.enums import AccessMethod, Track
from news_insight.sources.models import Source
from tests.factories import build_source

PLATFORMS = {
    "mastodon": ("Mastodon gGmbH", AccessMethod.ACTIVITYPUB),
    "bluesky": ("Bluesky Social PBC", AccessMethod.ATPROTO),
    "hn": ("Algolia (HN Search)", AccessMethod.JSON_API),
    "threads": ("Meta Platforms", AccessMethod.CRAWLER),
}


class FixedHeat:
    """Every post the same z (the platform norms need a week of live data)."""

    def __init__(self, z: float = 1.0, per_item: dict[int, float] | None = None) -> None:
        self._z, self._per_item = z, per_item or {}

    def z(self, item_ids: Iterable[int]) -> dict[int, float]:
        return {i: self._per_item.get(i, self._z) for i in item_ids}


def source(db_session: Session, key: str, *, track: Track = Track.COMMUNITY) -> Source:
    existing = db_session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if existing is not None:
        return existing
    operator, method = PLATFORMS.get(key, ("Example Media Inc.", AccessMethod.FEED))
    row = build_source(
        key=key,
        name=key,
        track=track,
        category="sns" if track is Track.COMMUNITY else "independent_media",
        operator=operator,
        access_method=method,
        official_domain=f"{key}.example",
    )
    db_session.add(row)
    db_session.flush()
    return row


def post(
    db_session: Session,
    key: str,
    n: int,
    *,
    when: datetime,
    title: str = "",
    author: str | None = None,
    link: str | None = None,
    metrics: dict[str, int] | None = None,
) -> Item:
    row = source(db_session, key)
    url = f"https://{key}.example/post/{n}"
    ingest_items(
        db_session,
        row,
        [
            RawItem(
                stable_id=url,
                url=url,
                title=title or f"{key}-{n}",  # too short to match by text
                author=author if author is not None else f"person{n}",
                link=link,
                metrics=metrics or {},
            )
        ],
        fetch_run=None,
        now=when,
        canary=False,
    )
    return db_session.scalars(select(Item).where(Item.url == url)).one()


def news(db_session: Session, n: int, *, when: datetime, url: str, title: str) -> Item:
    row = source(db_session, "wire", track=Track.NEWS)
    ingest_items(
        db_session,
        row,
        [RawItem(stable_id=url, url=url, title=title)],
        fetch_run=None,
        now=when,
        canary=False,
    )
    return db_session.scalars(select(Item).where(Item.url == url)).one()
