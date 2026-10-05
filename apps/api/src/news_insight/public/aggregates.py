"""Facet counts and the insight panel, computed live from cards (R3 will swap in rollups)."""

from typing import Any

from sqlalchemy import ColumnElement, func, select, true
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.public.filters import AXES, ReaderFilters, in_window, joined
from news_insight.public.keywords import keyword_element
from news_insight.public.periods import Window
from news_insight.public.schemas import Count, Insights, KeywordTrend
from news_insight.sources.models import Source
from news_insight.technologies.service import labels_for

KEYWORD_TOP = 6
KEYWORD_MIN_COUNT = 2
RELATED_TOP = 8


def _grouped(session: Session, key: Any, conditions: list[ColumnElement[bool]]) -> dict[str, int]:
    statement = joined(select(key, func.count(func.distinct(Item.id))))
    rows = session.execute(statement.where(*conditions).group_by(key)).tuples()
    return {str(value): int(count) for value, count in rows if value is not None}


def _axis_counts(
    session: Session, axis: str, conditions: list[ColumnElement[bool]]
) -> dict[str, int]:
    if axis == "theme":
        element = (
            func.jsonb_array_elements_text(ItemCard.themes).table_valued("value").lateral("element")
        )
        statement = (
            joined(select(element.c.value, func.count(func.distinct(Item.id))))
            .join(element, true())
            .where(*conditions)
            .group_by(element.c.value)
        )
        return {str(value): int(count) for value, count in session.execute(statement).tuples()}
    key: Any = {
        "field": ItemCard.field,
        "impact": ItemCard.impact,
        "signal": ItemCard.signal_type,
        "track": Item.track,
        "region": Source.region,
    }[axis]
    return _grouped(session, key, conditions)


def _ordered(counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def facets(session: Session, filters: ReaderFilters, window: Window) -> dict[str, dict[str, int]]:
    period = in_window(window)
    result = {
        axis: _ordered(_axis_counts(session, axis, [*filters.conditions(skip=axis), *period]))
        for axis in AXES
    }
    everything = ReaderFilters(scope="all", values=filters.values, q=filters.q)
    result["scope"] = _ordered(
        _grouped(session, ItemCard.scope, [*everything.conditions(), *period])
    )
    return result


def keyword_counts(session: Session, conditions: list[ColumnElement[bool]]) -> dict[str, int]:
    """Items per normalized keyword; labels are looked up later, only for the keys shown."""
    element = keyword_element("kw")
    normalized = element.c.value
    statement = (
        joined(
            select(
                normalized,
                func.count(func.distinct(Item.id)),
            )
        )
        .join(element, true())
        .where(*conditions)
        .group_by(normalized)
    )
    return {str(key): int(count) for key, count in session.execute(statement).tuples() if key}


def _total(session: Session, conditions: list[ColumnElement[bool]]) -> int:
    return (
        session.scalar(joined(select(func.count(func.distinct(Item.id)))).where(*conditions)) or 0
    )


def insights(session: Session, filters: ReaderFilters, window: Window) -> Insights:
    current = [*filters.conditions(), *in_window(window)]
    previous_window = window.previous() if window.start is not None else None
    previous = [*filters.conditions(), *in_window(previous_window)] if previous_window else None

    now_keywords = keyword_counts(session, current)
    before = keyword_counts(session, previous) if previous is not None else {}
    ranked = sorted(now_keywords.items(), key=lambda pair: (-pair[1], pair[0]))
    top = [(key, count) for key, count in ranked if count >= KEYWORD_MIN_COUNT][:KEYWORD_TOP]
    top_keys = {key for key, _ in top}
    related = [key for key, _ in ranked if key not in top_keys][:RELATED_TOP]
    # labels only for what is shown: a busy week has tens of thousands of keys (2026-10-05)
    labels = labels_for(session, [*top_keys, *related])

    def trend(key: str, label: str, count: int) -> KeywordTrend:
        if previous is None:
            return KeywordTrend(
                key=key, label=label, count=count, previous=None, change=None, is_new=False
            )
        prior = before.get(key, 0)
        change = round((count - prior) / prior * 100, 1) if prior else None
        return KeywordTrend(
            key=key, label=label, count=count, previous=prior, change=change, is_new=prior == 0
        )

    def counts(values: dict[str, int]) -> list[Count]:
        return [Count(key=key, count=count) for key, count in _ordered(values).items()]

    return Insights(
        total=_total(session, current),
        previous_total=_total(session, previous) if previous is not None else None,
        keywords=[trend(key, labels[key], count) for key, count in top],
        related_keywords=[labels[key] for key in related],
        fields=counts(_grouped(session, ItemCard.field, current)),
        signal_types=counts(_axis_counts(session, "signal", current)),
        impacts=counts(_grouped(session, ItemCard.impact, current)),
    )
