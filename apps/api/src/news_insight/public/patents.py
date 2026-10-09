"""Patent signals (plan 16 #5): publications from the patent-office collector (EPO OPS for
US, EP and CN) and cards the engines marked as intellectual property, counted by
month or quarter, by technology area and by company. The collectors run only once their free
keys are in .env; the `ip` cards from news, blogs and the EPO pilot count from the start."""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import info_for
from news_insight.content.models import Item
from news_insight.public.feed import feed
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import Window, calendar_window, current_key, trailing_windows
from news_insight.public.schemas import CompanyRef, FeedPage
from news_insight.sources.models import Source
from news_insight.taxonomy.models import CardLabel, TaxNode, TaxScheme

Kind = Literal["month", "quarter"]
OFFICE_CATEGORIES = ("patent_office", "ip_office")
PERIODS = {"month": 12, "quarter": 8}
TOP = 15


def patent_condition() -> ColumnElement[bool]:
    return or_(ItemCard.signal_type == "ip", Source.category.in_(OFFICE_CATEGORIES))


class PeriodCount(BaseModel):
    key: str
    total: int
    office: int  # from patent-office collectors (the rest: news about patents)


class Trend(BaseModel):
    key: str
    label: str
    axis: str = "company"  # field | theme for technology areas (the explore filter to open)
    counts: list[int]  # one per period, oldest first
    current: int
    previous: int


class CompanyTrend(Trend):
    company: CompanyRef


class PatentView(BaseModel):
    kind: Kind
    periods: list[PeriodCount]
    nodes: list[Trend]
    companies: list[CompanyTrend]
    recent: FeedPage


def _windows(kind: Kind, now: datetime) -> list[Window]:
    return trailing_windows(calendar_window(kind, current_key(kind, now)), PERIODS[kind])


def _trend(key: str, label: str, counts: list[int], axis: str = "company") -> Trend:
    return Trend(
        key=key,
        label=label,
        axis=axis,
        counts=counts,
        current=counts[-1],
        previous=counts[-2] if len(counts) > 1 else 0,
    )


def patent_view(session: Session, *, kind: Kind, now: datetime, page: int = 1) -> PatentView:
    windows = _windows(kind, now)
    start, end = windows[0].start, windows[-1].end
    assert start is not None
    base = [*ReaderFilters(scope="all").conditions(), patent_condition()]
    rows = session.execute(
        joined(select(Item.id, Item.first_seen_at, Source.category, ItemCard.company_keys)).where(
            *base,
            ItemCard.scope != "irrelevant",
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
        )
    ).all()

    def slot(moment: datetime) -> int:
        for index, window in enumerate(windows):
            if window.start is not None and window.start <= moment < window.end:
                return index
        return -1

    slots = {row.id: slot(row.first_seen_at) for row in rows}
    totals, offices = Counter[int](), Counter[int]()
    company_counts: dict[str, list[int]] = defaultdict(lambda: [0] * len(windows))
    for row in rows:
        index = slots[row.id]
        totals[index] += 1
        if row.category in OFFICE_CATEGORIES:
            offices[index] += 1
        for key in row.company_keys or []:
            company_counts[key][index] += 1

    # technology areas: each label rolls up to its second-level node (the theme)
    theme = func.coalesce(TaxNode.path[2], TaxNode.id)
    label_rows = (
        session.execute(
            select(CardLabel.item_id, theme)
            .join(TaxNode, TaxNode.id == CardLabel.node_id)
            .join(TaxScheme, TaxScheme.id == TaxNode.scheme_id)
            .where(TaxScheme.key == "technology", CardLabel.item_id.in_(list(slots)))
            .distinct()
        )
        .tuples()
        .all()
        if slots
        else []
    )
    node_counts: dict[int, list[int]] = defaultdict(lambda: [0] * len(windows))
    for item_id, node_id in label_rows:
        node_counts[node_id][slots[item_id]] += 1
    nodes = {
        node.id: node
        for node in session.scalars(select(TaxNode).where(TaxNode.id.in_(list(node_counts))))
    }
    node_trends = sorted(
        (
            _trend(
                nodes[i].key, nodes[i].label, counts, "field" if nodes[i].depth == 1 else "theme"
            )
            for i, counts in node_counts.items()
            if i in nodes
        ),
        key=lambda t: (sum(t.counts[-3:]), sum(t.counts)),
        reverse=True,
    )[:TOP]

    infos = info_for(session, set(company_counts))
    company_trends = sorted(
        (
            CompanyTrend(
                **_trend(key, infos[key].name_ko or infos[key].name, counts).model_dump(),
                company=CompanyRef(
                    key=key,
                    label=infos[key].name_ko or infos[key].name,
                    relation=infos[key].relation,
                    kind=infos[key].kind,
                ),
            )
            for key, counts in company_counts.items()
            if key in infos
        ),
        key=lambda t: (sum(t.counts[-3:]), sum(t.counts)),
        reverse=True,
    )[:TOP]

    recent_window = Window(kind=kind, key="patents", start=start, end=end)
    recent = feed(
        session,
        ReaderFilters(scope="all"),
        recent_window,
        sort="recent",
        page=page,
        size=20,
        extra=[patent_condition(), ItemCard.scope != "irrelevant"],
    )
    return PatentView(
        kind=kind,
        periods=[
            PeriodCount(key=w.key, total=totals[i], office=offices[i])
            for i, w in enumerate(windows)
        ],
        nodes=node_trends,
        companies=company_trends,
        recent=recent,
    )
