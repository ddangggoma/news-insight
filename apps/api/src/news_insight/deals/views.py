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
from news_insight.deals.clean import fold, same_party, script
from news_insight.deals.extract import UNDISCLOSED
from news_insight.deals.models import Deal
from news_insight.public.periods import KST
from news_insight.sources.models import Source

PAIRED = ("partnership", "joint_venture", "licensing")
DAY_WINDOW = 21  # reports of one deal land within three weeks of each other
SIZE_RATIO = 1.15  # "약 1.1억 달러" and "1억 달러" are one round
# from this size deals are rare enough that the same amount (within BIG_RATIO) in the same
# weeks is the same deal whatever the names say ($1B rounds are too common for this)
BIG_USD = 10e9
BIG_RATIO = 1.02


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
    return key or fold(name)


def _parties(deal: Deal) -> list[tuple[str | None, str | None]]:
    """Whom the deal is about: the target of an investment, acquisition or listing (the
    actor is left out so an undisclosed investor merges), both sides of a partnership."""
    actor = (deal.actor, deal.actor_key)
    target = (deal.counterparty, deal.counterparty_key) if deal.counterparty else actor
    if deal.kind in PAIRED:
        return sorted({actor, target}, key=lambda p: _ident(*p))
    return [target]


def _party_match(a: tuple[str | None, str | None], b: tuple[str | None, str | None]) -> bool:
    if a[1] and b[1]:
        return a[1] == b[1]  # both in the registry: the keys decide
    return (
        same_party(a[0], b[0])
        or bool(a[1] and a[1] == fold(b[0]))
        or bool(b[1] and b[1] == fold(a[0]))
    )


def _sized_alike(a: Deal, b: Deal) -> bool:
    x, y = a.amount_usd, b.amount_usd
    if x is None or y is None:
        return x is None and y is None
    return max(x, y) <= SIZE_RATIO * min(x, y)


def same_deal(a: Deal, b: Deal, *, sized: bool = True) -> bool:
    """Two reports of one deal: same kind, announced within DAY_WINDOW of each other, the
    same parties however spelled, and amounts within SIZE_RATIO (`sized=False` sets the
    amounts aside, to fit an unsized report to a group). Two large deals of one kind with
    the same amount in the same weeks are one deal when their names, written in other
    scripts, cannot be compared (파라마운트 / Paramount / 派拉蒙)."""
    if a.kind != b.kind:
        return False
    days = (a.announced_on - b.announced_on).days if a.announced_on and b.announced_on else 0
    if abs(days) > DAY_WINDOW:
        return False
    if sized and not _sized_alike(a, b):
        return False
    pa, pb = _parties(a), _parties(b)
    if len(pa) == len(pb) and all(_party_match(x, y) for x, y in zip(pa, pb, strict=True)):
        return True
    x, y = a.amount_usd or 0, b.amount_usd or 0
    if sized and min(x, y) >= BIG_USD and max(x, y) <= BIG_RATIO * min(x, y):
        # only names that cannot be compared: other scripts, neither in the registry (a
        # registered company would have matched the other spelling through its aliases)
        if any(k for _, k in pa + pb) or len(pa) != 1 or len(pb) != 1:
            return False
        return script(pa[0][0]) != script(pb[0][0])
    return False


def _blocks(deal: Deal) -> list[tuple[Any, ...]]:
    """Candidate buckets, so only plausible pairs are compared."""
    out: list[tuple[Any, ...]] = [(deal.kind, "p", fold(name)[:3]) for name, _ in _parties(deal)]
    out += [(deal.kind, "k", key) for _, key in _parties(deal) if key]
    if deal.amount_usd and deal.amount_usd >= BIG_USD:
        out.append((deal.kind, "s", round(math.log10(deal.amount_usd), 1)))
        out.append((deal.kind, "s", round(math.log10(deal.amount_usd) + 0.05, 1)))
    return out


Row = tuple[Any, ...]  # (Deal, title, source, url, ...) with the deal first


def dedupe(rows: list[Row]) -> list[Row]:
    parent = list(range(len(rows)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    blocks: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        for block in set(_blocks(row[0])):
            blocks[block].append(i)
    for members in blocks.values():
        for x, i in enumerate(members):
            for j in members[x + 1 :]:
                if root(i) != root(j) and same_deal(rows[i][0], rows[j][0]):
                    parent[root(j)] = root(i)
    # an unsized report joins the sized group it matches, when exactly one does
    for i, row in enumerate(rows):
        if row[0].amount_usd is not None:
            continue
        fits = set()
        for block in set(_blocks(row[0])):
            for j in blocks[block]:
                other = rows[j][0]
                if other.amount_usd is not None and same_deal(row[0], other, sized=False):
                    fits.add(root(j))
        if len(fits) == 1:
            parent[root(i)] = fits.pop()

    groups: dict[int, list[Row]] = defaultdict(list)
    for i, row in enumerate(rows):
        groups[root(i)].append(row)
    out = []
    for group in groups.values():
        known = [m for m in group if m[0].actor != UNDISCLOSED]
        sized = [m for m in known if m[0].amount_usd]
        lead = (sized or known or group)[-1]  # rows are newest first: the earliest report leads
        out.append((*lead, len(group)))
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
                key or fold(label), Party(name=label, key=key, count=0, usd=0, kinds={})
            )
            party.count += 1
            party.usd += deal.amount_usd or 0
            party.kinds[deal.kind] = party.kinds.get(deal.kind, 0) + 1
        if deal.counterparty and deal.actor != UNDISCLOSED:
            a = _label(deal.actor, deal.actor_key, infos)
            b = _label(deal.counterparty, deal.counterparty_key, infos)
            ident = (deal.actor_key or fold(a), deal.counterparty_key or fold(b))
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
