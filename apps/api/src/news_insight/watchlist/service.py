"""The reader's watch list (plan 13 A5): what to follow, and what today's reports say about it.

Managed in the console only (the reader pages are public); shown on the briefing as
"내 관심 항목". No mail or push: the user decided against alerts on 2026-10-05.
"""

from collections import Counter
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.companies.catalog import ORGANIZATIONS, CompanyKind
from news_insight.companies.models import Company
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item
from news_insight.taxonomy.catalog import LABELS, THEME_KEYS
from news_insight.technologies.catalog import normalize
from news_insight.technologies.service import alias_map
from news_insight.watchlist.models import WatchItem

KINDS = ("company", "theme", "keyword")
RELEVANT = ("dx", "dx_dependency")
TOP_ITEMS = 3


class WatchOut(BaseModel):
    id: int
    kind: str
    key: str
    label: str


class WatchHit(BaseModel):
    kind: str
    key: str
    label: str
    count: int
    item_ids: list[int]


class Suggestion(BaseModel):
    kind: str
    key: str
    label: str
    count: int


class WatchError(ValueError):
    """A watch item that does not name a known company, theme or keyword."""


def items(session: Session) -> list[WatchOut]:
    rows = session.scalars(select(WatchItem).order_by(WatchItem.kind, WatchItem.label))
    return [WatchOut(id=w.id, kind=w.kind, key=w.key, label=w.label) for w in rows]


def add(session: Session, *, kind: str, value: str) -> WatchOut:
    """`value` is a company key, a theme key, or free keyword text (normalised like card
    keywords, so "AI 에이전트" follows the same key the radar uses)."""
    value = value.strip()
    if kind == "company":
        company = session.get(Company, value)
        if company is None:
            raise WatchError(f"unknown company '{value}'")
        key, label = company.key, company.name_ko or company.name
    elif kind == "theme":
        if value not in THEME_KEYS:
            raise WatchError(f"unknown theme '{value}'")
        key, label = value, LABELS.get(value, value)
    elif kind == "keyword":
        normalized = normalize(value)
        if len(normalized) < 2:
            raise WatchError("keyword too short")
        key, label = alias_map(session).get(normalized, normalized)[:80], value[:120]
    else:
        raise WatchError(f"unknown kind '{kind}'")
    existing = session.scalars(
        select(WatchItem).where(WatchItem.kind == kind, WatchItem.key == key)
    ).first()
    item = existing or WatchItem(kind=kind, key=key, label=label)
    if existing is None:
        session.add(item)
        session.flush()
    return WatchOut(id=item.id, kind=item.kind, key=item.key, label=item.label)


def remove(session: Session, watch_id: int) -> bool:
    item = session.get(WatchItem, watch_id)
    if item is None:
        return False
    session.delete(item)
    session.flush()
    return True


def _condition(kind: str, key: str) -> ColumnElement[bool]:
    if kind == "company":
        return ItemCard.company_keys.contains([key])
    if kind == "theme":
        return ItemCard.themes.contains([key])
    return ItemCard.technology_keys.contains([key])


def hits(session: Session, *, start: datetime, end: datetime) -> list[WatchHit]:
    """Reports on each watched subject among the DX-relevant cards first seen in [start, end),
    most relevant first; subjects with no report are left out."""
    found: list[WatchHit] = []
    for watch in session.scalars(select(WatchItem).order_by(WatchItem.id)):
        base = (
            select(Item.id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .where(
                Item.first_seen_at >= start,
                Item.first_seen_at < end,
                ItemCard.status == CardStatus.READY,
                ItemCard.scope.in_(RELEVANT),
                fresh_condition(),
                _condition(watch.kind, watch.key),
            )
        )
        count = session.scalar(select(func.count()).select_from(base.subquery())) or 0
        if not count:
            continue
        top = session.scalars(
            base.order_by(ItemCard.relevance.desc().nulls_last(), Item.id.desc()).limit(TOP_ITEMS)
        ).all()
        found.append(
            WatchHit(
                kind=watch.kind, key=watch.key, label=watch.label, count=count, item_ids=list(top)
            )
        )
    found.sort(key=lambda h: -h.count)
    return found


def suggestions(
    session: Session, *, now: datetime, days: int = 7, limit: int = 10
) -> list[Suggestion]:
    """Companies (not institutes or regulators) and themes most reported on lately and not yet
    watched: a starting point for an empty list."""
    watched = {(w.kind, w.key) for w in session.scalars(select(WatchItem))}
    since = now - timedelta(days=days)
    recent = (
        select(ItemCard.company_keys, ItemCard.themes)
        .join(Item, Item.id == ItemCard.item_id)
        .where(
            Item.first_seen_at >= since,
            ItemCard.status == CardStatus.READY,
            ItemCard.scope.in_(RELEVANT),
        )
    )
    companies: Counter[str] = Counter()
    themes: Counter[str] = Counter()
    for keys, card_themes in session.execute(recent).tuples():
        companies.update(keys or [])
        themes.update(card_themes or [])
    registry = {
        c.key: c
        for c in session.scalars(select(Company).where(Company.key.in_(list(companies))))
        if CompanyKind(c.kind) not in ORGANIZATIONS
    }
    out = [
        Suggestion(kind="company", key=k, label=registry[k].name_ko or registry[k].name, count=n)
        for k, n in companies.most_common()
        if k in registry and ("company", k) not in watched
    ][:limit]
    out += [
        Suggestion(kind="theme", key=k, label=LABELS.get(k, k), count=n)
        for k, n in themes.most_common()
        if ("theme", k) not in watched
    ][: limit // 2]
    return out
