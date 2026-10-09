"""Deal views (plan 16 #8): counts and rough sizes by kind and month, the most active
parties, the pairs that deal with each other, and the list with its evidence cards."""

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import info_for
from news_insight.content.models import Item
from news_insight.deals.extract import UNDISCLOSED
from news_insight.deals.models import Deal
from news_insight.public.periods import KST
from news_insight.sources.models import Source


class KindCount(BaseModel):
    kind: str
    count: int
    usd: float  # rough sum of the deals with a known amount
    sized: int  # how many had an amount


class MonthCount(BaseModel):
    month: str
    counts: dict[str, int]


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


class DealView(BaseModel):
    days: int
    total: int
    kinds: list[KindCount]
    months: list[MonthCount]
    parties: list[Party]
    pairs: list[Pair]
    deals: list[DealOut]


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


def dedupe(rows: list[tuple[Deal, str, str, str]]) -> list[tuple[Deal, str, str, str, int]]:
    groups: dict[tuple[Any, ...], list[tuple[Deal, str, str, str]]] = {}
    for row in rows:
        groups.setdefault(same_deal_key(row[0]), []).append(row)
    out = []
    for members in groups.values():
        known = [m for m in members if m[0].actor != UNDISCLOSED]
        lead = (known or members)[-1]  # rows are newest first: the earliest report leads
        out.append((*lead, len(members)))
    out.sort(key=lambda r: (r[0].announced_on or date.min, r[0].id), reverse=True)
    return out


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
    since = (now.astimezone(KST) - timedelta(days=days)).date()
    conditions = [Deal.announced_on >= since]
    if kind:
        conditions.append(Deal.kind == kind)
    if company:
        conditions.append(or_(Deal.actor_key == company, Deal.counterparty_key == company))
    rows = (
        session.execute(
            select(Deal, func.coalesce(ItemCard.title_ko, Item.title), Source.name, Item.url)
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
    months: dict[str, Counter[str]] = defaultdict(Counter)
    parties: dict[str, Party] = {}
    pairs: dict[tuple[str, str], Pair] = {}
    for deal, *_ in merged:
        k = kinds.setdefault(deal.kind, KindCount(kind=deal.kind, count=0, usd=0, sized=0))
        k.count += 1
        if deal.amount_usd:
            k.usd += deal.amount_usd
            k.sized += 1
        if deal.announced_on:
            months[deal.announced_on.strftime("%Y-%m")][deal.kind] += 1
        sides = [] if deal.actor == UNDISCLOSED else [(deal.actor, deal.actor_key)]
        if deal.counterparty:
            sides.append((deal.counterparty, deal.counterparty_key))
        for name, key in sides:
            label = _label(name, key, infos)
            party = parties.setdefault(
                key or label.lower(), Party(name=label, key=key, count=0, usd=0, kinds={})
            )
            party.count += 1
            party.usd += deal.amount_usd or 0
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
    return DealView(
        days=days,
        total=len(merged),
        kinds=sorted(kinds.values(), key=lambda k: k.count, reverse=True),
        months=[MonthCount(month=m, counts=dict(c)) for m, c in sorted(months.items())],
        parties=sorted(parties.values(), key=lambda p: (p.count, p.usd), reverse=True)[:15],
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
            )
            for deal, title, source, url, reports in merged[:100]
        ],
    )
