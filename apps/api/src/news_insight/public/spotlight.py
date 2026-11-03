"""Spotlight for readers (plan 18): the latest published day's Top 10 per section, each entry
marked against the immediately preceding calendar day. Failed rows are never shown."""

import datetime as dt
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.public.periods import KST
from news_insight.spotlight.candidates import SECTIONS
from news_insight.spotlight.models import Spotlight, SpotlightEntry, SpotlightStatus

AVAILABLE_DATES = 60
Change = Literal["new", "up", "down", "same"]


class SpotlightNotFound(LookupError):
    """No published spotlight on the requested date."""


class SpotlightEntryOut(BaseModel):
    rank: int
    stat_rank: int
    change: Change
    change_by: int  # places moved against the day before; 0 for same and new
    key: str
    item_ids: list[int]
    title_ko: str
    product_name: str | None
    summary: str
    why_hot: str
    rank_note: str | None
    metrics: dict[str, Any]
    fallback: bool
    url: str | None  # the original of the representative item (item_ids[0])


class SpotlightView(BaseModel):
    date: dt.date | None
    generating: bool  # today's (KST) spotlight is not published yet
    headline: str
    benchmark_note: str
    sections: dict[str, list[SpotlightEntryOut]]
    available_dates: list[dt.date]  # newest first
    generated_at: datetime | None


def _published(session: Session, day: date | None = None) -> Spotlight | None:
    query = select(Spotlight).where(Spotlight.status == SpotlightStatus.PUBLISHED)
    if day is not None:
        query = query.where(Spotlight.spotlight_date == day)
    return session.scalars(query.order_by(Spotlight.spotlight_date.desc()).limit(1)).first()


def _change(entry: SpotlightEntry, before: dict[tuple[str, str], int]) -> tuple[Change, int]:
    was = before.get((entry.section, entry.key))
    if was is None:
        return "new", 0
    if entry.rank < was:
        return "up", was - entry.rank
    if entry.rank > was:
        return "down", entry.rank - was
    return "same", 0


def spotlight_view(session: Session, *, day: date | None, now: datetime) -> SpotlightView:
    spotlight = _published(session, day)
    if spotlight is None and day is not None:
        raise SpotlightNotFound(day.isoformat())
    available = list(
        session.scalars(
            select(Spotlight.spotlight_date)
            .where(Spotlight.status == SpotlightStatus.PUBLISHED)
            .order_by(Spotlight.spotlight_date.desc())
            .limit(AVAILABLE_DATES)
        )
    )
    sections: dict[str, list[SpotlightEntryOut]] = {section: [] for section in SECTIONS}
    if spotlight is None:
        return SpotlightView(
            date=None,
            generating=True,
            headline="",
            benchmark_note="",
            sections=sections,
            available_dates=available,
            generated_at=None,
        )

    entries = list(
        session.scalars(
            select(SpotlightEntry)
            .where(SpotlightEntry.spotlight_id == spotlight.id)
            .order_by(SpotlightEntry.section, SpotlightEntry.rank)
        )
    )
    previous = _published(session, spotlight.spotlight_date - timedelta(days=1))
    before: dict[tuple[str, str], int] = {}
    if previous is not None:
        before = {
            (row.section, row.key): row.rank
            for row in session.scalars(
                select(SpotlightEntry).where(SpotlightEntry.spotlight_id == previous.id)
            )
        }
    lead_ids = {entry.item_ids[0] for entry in entries if entry.item_ids}
    urls: dict[int, str] = {}
    if lead_ids:
        urls = {
            row.id: row.url
            for row in session.execute(select(Item.id, Item.url).where(Item.id.in_(lead_ids)))
        }
    for entry in entries:
        change, change_by = _change(entry, before)
        sections.setdefault(entry.section, []).append(
            SpotlightEntryOut(
                rank=entry.rank,
                stat_rank=entry.stat_rank,
                change=change,
                change_by=change_by,
                key=entry.key,
                item_ids=entry.item_ids,
                title_ko=entry.title_ko,
                product_name=entry.product_name,
                summary=entry.summary,
                why_hot=entry.why_hot,
                rank_note=entry.rank_note,
                metrics=entry.metrics,
                fallback=entry.fallback,
                url=urls.get(entry.item_ids[0]) if entry.item_ids else None,
            )
        )
    return SpotlightView(
        date=spotlight.spotlight_date,
        generating=day is None and now.astimezone(KST).date() > spotlight.spotlight_date,
        headline=spotlight.headline,
        benchmark_note=spotlight.benchmark_note,
        sections=sections,
        available_dates=available,
        generated_at=spotlight.generated_at,
    )
