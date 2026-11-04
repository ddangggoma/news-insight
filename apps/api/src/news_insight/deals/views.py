"""Deal views (plan 16 #8): counts and rough sizes by kind, week and month, the most active
parties, the pairs that deal with each other, and the list with its evidence cards.

A deal is dated by the day it was announced; one without that date falls back to its
evidence article's date (published, or first seen when the publisher's date is missing or
later than that)."""

import math
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import info_for
from news_insight.content.models import Item
from news_insight.deals.extract import UNDISCLOSED
from news_insight.deals.models import Deal
from news_insight.public.periods import KST
from news_insight.sources.models import Source

# A dollar size this large is almost always a misread (a valuation or market cap taken for the
# amount raised): such deals are listed and flagged but left out of every sum and average.
OUTLIER_USD = 50e9


class KindCount(BaseModel):
    kind: str
    count: int
    usd: float  # rough sum of the deals with a known amount
    sized: int  # how many had an amount


class MonthCount(BaseModel):
    month: str
    counts: dict[str, int]


class WeekCount(BaseModel):
    week: str  # the Monday that starts it, YYYY-MM-DD
    counts: dict[str, int]
    usd: float  # rough sum of the deals with a known amount


class DealStats(BaseModel):
    sized: int  # deals with a known amount
    usd: float  # their rough sum
    median_usd: float | None
    mean_usd: float | None
    max_usd: float | None
    companies: int  # distinct named parties (uncapped, unlike `parties`)
    pairs: int  # distinct actor -> counterparty pairs
    outliers: int = 0  # amounts >= OUTLIER_USD, left out of the sums above


class Party(BaseModel):
    name: str
    key: str | None
    count: int
    usd: float
    kinds: dict[str, int]


class Pair(BaseModel):
    actor: str
    actor_key: str | None
    counterparty: str
    counterparty_key: str | None
    count: int
    kinds: list[str]


class DealOut(BaseModel):
    id: int
    kind: str
    actor: str
    actor_key: str | None
    counterparty: str | None
    counterparty_key: str | None
    amount: float | None
    currency: str | None
    amount_usd: float | None
    stage: str | None
    announced_on: date | None
    summary: str
    item_id: int
    title: str
    source: str
    url: str
    reports: int = 1  # cards reporting the same deal
    outlier: bool = False  # amount_usd >= OUTLIER_USD: likely a misread, not summed
    occurred_on: date | None = None  # announced_on, or the evidence article's date


class DealView(BaseModel):
    days: int
    total: int
    kinds: list[KindCount]
    months: list[MonthCount]
    parties: list[Party]
    pairs: list[Pair]
    deals: list[DealOut]
    weeks: list[WeekCount] = []
    stats: DealStats | None = None
    top_usd: list[Party] = []  # the parties with the largest disclosed sums


def _ident(name: str | None, key: str | None) -> str:
    return key or " ".join((name or "").lower().split())


def same_deal_key(deal: Deal) -> tuple[Any, ...]:
    """Reports of one deal: same kind, target (or the pair, for partnerships), amount within
    a few percent and month. The actor is left out so an undisclosed investor merges."""
    target = _ident(deal.counterparty, deal.counterparty_key) or _ident(deal.actor, deal.actor_key)
    if deal.kind in ("partnership", "joint_venture", "licensing"):
        target = "|".join(sorted({_ident(deal.actor, deal.actor_key), target}))
    size = round(math.log10(deal.amount_usd), 1) if deal.amount_usd else None
    month = deal.announced_on.strftime("%Y-%m") if deal.announced_on else None
    return (deal.kind, target, size, month)


Row = tuple[Any, ...]  # (Deal, title, source, url, ...) with the deal first


def dedupe(rows: list[Row]) -> list[Row]:
    groups: dict[tuple[Any, ...], list[Row]] = {}
    for row in rows:
        groups.setdefault(same_deal_key(row[0]), []).append(row)
    out = []
    for members in groups.values():
        known = [m for m in members if m[0].actor != UNDISCLOSED]
        lead = (known or members)[-1]  # rows are newest first: the earliest report leads
        out.append((*lead, len(members)))
    out.sort(key=lambda r: (r[0].announced_on or date.min, r[0].id), reverse=True)
    return out


def item_day(published_at: datetime | None, first_seen_at: datetime | None) -> date | None:
    """An evidence article's KST date: when it was published, unless that is missing or
    later than when it was first seen (a bad publisher date)."""
    moment = published_at
    if moment is None or (first_seen_at is not None and moment > first_seen_at):
        moment = first_seen_at
    return moment.astimezone(KST).date() if moment is not None else None


def deal_day(
    deal: Deal, published_at: datetime | None, first_seen_at: datetime | None
) -> date | None:
    return deal.announced_on or item_day(published_at, first_seen_at)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _month_keys(since: date, today: date) -> list[str]:
    keys, year, month = [], since.year, since.month
    while (year, month) <= (today.year, today.month):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return keys


def counted_usd(deal: Deal) -> float:
    """The dollar size that enters sums: 0 when unknown or an outlier."""
    if not deal.amount_usd or deal.amount_usd >= OUTLIER_USD:
        return 0
    return deal.amount_usd


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _label(name: str | None, key: str | None, infos: dict[str, Any]) -> str:
    if key and key in infos:
        return str(infos[key].name_ko or infos[key].name)
    return name or ""


def deal_view(
    session: Session,
    *,
    days: int,
    now: datetime,
    kind: str | None = None,
    company: str | None = None,
) -> DealView:
    today = now.astimezone(KST).date()
    since = today - timedelta(days=days)
    since_at = datetime.combine(since, datetime.min.time(), tzinfo=KST)
    conditions = [
        or_(
            Deal.announced_on >= since,
            and_(Deal.announced_on.is_(None), Item.first_seen_at >= since_at),
        )
    ]
    if kind:
        conditions.append(Deal.kind == kind)
    if company:
        conditions.append(or_(Deal.actor_key == company, Deal.counterparty_key == company))
    rows = (
        session.execute(
            select(
                Deal,
                func.coalesce(ItemCard.title_ko, Item.title),
                Source.name,
                Item.url,
                Item.published_at,
                Item.first_seen_at,
            )
            .join(Item, Item.id == Deal.item_id)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .where(*conditions)
            .order_by(Deal.announced_on.desc(), Deal.id.desc())
        )
        .tuples()
        .all()
    )
    merged = dedupe(list(rows))
    keys = {k for deal, *_ in merged for k in (deal.actor_key, deal.counterparty_key) if k}
    infos = info_for(session, keys)

    kinds: dict[str, KindCount] = {}
    months: dict[str, Counter[str]] = {key: Counter() for key in _month_keys(since, today)}
    weeks: dict[date, WeekCount] = {}
    monday = week_start(since)
    while monday <= today:
        weeks[monday] = WeekCount(week=monday.isoformat(), counts={}, usd=0)
        monday += timedelta(days=7)
    amounts: list[float] = []
    outliers = 0
    parties: dict[str, Party] = {}
    pairs: dict[tuple[str, str], Pair] = {}
    days_of = {
        deal.id: deal_day(deal, published, seen) for deal, _, _, _, published, seen, _ in merged
    }
    for deal, *_ in merged:
        k = kinds.setdefault(deal.kind, KindCount(kind=deal.kind, count=0, usd=0, sized=0))
        k.count += 1
        size = counted_usd(deal)
        if size:
            k.usd += size
            k.sized += 1
            amounts.append(size)
        elif deal.amount_usd:
            outliers += 1
        day = days_of[deal.id]
        if day:
            months.setdefault(day.strftime("%Y-%m"), Counter())[deal.kind] += 1
            week = weeks.get(week_start(day))
            if week is not None:
                week.counts[deal.kind] = week.counts.get(deal.kind, 0) + 1
                week.usd += size
        sides = [] if deal.actor == UNDISCLOSED else [(deal.actor, deal.actor_key)]
        if deal.counterparty:
            sides.append((deal.counterparty, deal.counterparty_key))
        for name, key in sides:
            label = _label(name, key, infos)
            party = parties.setdefault(
                key or label.lower(), Party(name=label, key=key, count=0, usd=0, kinds={})
            )
            party.count += 1
            party.usd += size
            party.kinds[deal.kind] = party.kinds.get(deal.kind, 0) + 1
        if deal.counterparty and deal.actor != UNDISCLOSED:
            a = _label(deal.actor, deal.actor_key, infos)
            b = _label(deal.counterparty, deal.counterparty_key, infos)
            ident = (deal.actor_key or a.lower(), deal.counterparty_key or b.lower())
            pair = pairs.setdefault(
                ident,
                Pair(
                    actor=a,
                    actor_key=deal.actor_key,
                    counterparty=b,
                    counterparty_key=deal.counterparty_key,
                    count=0,
                    kinds=[],
                ),
            )
            pair.count += 1
            if deal.kind not in pair.kinds:
                pair.kinds.append(deal.kind)
    ranked = sorted(parties.values(), key=lambda p: (p.count, p.usd), reverse=True)
    return DealView(
        days=days,
        total=len(merged),
        kinds=sorted(kinds.values(), key=lambda k: k.count, reverse=True),
        months=[MonthCount(month=m, counts=dict(c)) for m, c in sorted(months.items())],
        parties=ranked[:15],
        pairs=sorted(pairs.values(), key=lambda p: p.count, reverse=True)[:15],
        deals=[
            DealOut(
                id=deal.id,
                kind=deal.kind,
                actor=_label(deal.actor, deal.actor_key, infos),
                actor_key=deal.actor_key,
                counterparty=_label(deal.counterparty, deal.counterparty_key, infos) or None,
                counterparty_key=deal.counterparty_key,
                amount=deal.amount,
                currency=deal.currency,
                amount_usd=deal.amount_usd,
                stage=deal.stage,
                announced_on=deal.announced_on,
                summary=deal.summary,
                item_id=deal.item_id,
                title=title,
                source=source,
                url=url,
                reports=reports,
                occurred_on=days_of[deal.id],
                outlier=bool(deal.amount_usd and deal.amount_usd >= OUTLIER_USD),
            )
            for deal, title, source, url, _, _, reports in merged[:100]
        ],
        weeks=list(weeks.values()),
        stats=DealStats(
            sized=len(amounts),
            usd=sum(amounts),
            median_usd=_median(amounts),
            mean_usd=sum(amounts) / len(amounts) if amounts else None,
            max_usd=max(amounts) if amounts else None,
            companies=len(parties),
            pairs=len(pairs),
            outliers=outliers,
        ),
        top_usd=sorted((p for p in ranked if p.usd > 0), key=lambda p: p.usd, reverse=True)[:8],
    )
