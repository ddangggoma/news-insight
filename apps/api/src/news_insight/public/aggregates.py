"""Facet counts and the insight panel, counted on the reader facts view (public/facts.py)."""

from typing import Any

from sqlalchemy import ColumnElement, and_, func, select, true, tuple_
from sqlalchemy.orm import Session

from news_insight.public import facts
from news_insight.public.facts import AXIS_COLUMNS, F
from news_insight.public.filters import AXES, ReaderFilters
from news_insight.public.periods import Window
from news_insight.public.schemas import Count, Insights, KeywordTrend
from news_insight.technologies.service import labels_for

KEYWORD_TOP = 6
KEYWORD_MIN_COUNT = 2
RELATED_TOP = 8


def _ordered(counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _counted(conditions: list[ColumnElement[bool]]) -> Any:
    return func.count().filter(and_(true(), *conditions))


def facets(session: Session, filters: ReaderFilters, window: Window) -> dict[str, dict[str, int]]:
    """Each axis counted without its own filter, the scope without the scope; one pass for
    every column axis, one for the themes (2026-11-03: was seven queries over the tables)."""
    shared = [*facts.in_window(window), *facts.common(filters)]
    groups = {**AXIS_COLUMNS, "scope": F.scope}
    counts = {
        axis: _counted(facts.narrowing(filters, skip=axis, scoped=axis != "scope"))
        for axis in groups
    }
    statement = (
        select(
            *(func.grouping(column) for column in groups.values()),
            *groups.values(),
            *counts.values(),
        )
        .where(*shared)
        .group_by(func.grouping_sets(*groups.values()))
    )
    found: dict[str, dict[str, int]] = {axis: {} for axis in groups}
    width = len(groups)
    for row in session.execute(statement):
        for index, axis in enumerate(groups):
            grouped, value, count = row[index], row[width + index], row[2 * width + index]
            if grouped == 0 and value is not None and count:
                found[axis][str(value)] = int(count)

    theme = func.jsonb_array_elements_text(F.themes).table_valued("value").lateral("theme")
    themes = (
        select(theme.c.value, func.count(func.distinct(F.item_id)))
        .select_from(facts.facts)
        .join(theme, true())
        .where(*shared, *facts.narrowing(filters, skip="theme"))
        .group_by(theme.c.value)
    )
    found["theme"] = {str(value): int(count) for value, count in session.execute(themes)}
    return {axis: _ordered(found[axis]) for axis in [*AXES, "scope"]}


def keyword_counts(
    session: Session, conditions: list[ColumnElement[bool]], only: set[str] | None = None
) -> dict[str, int]:
    """Items per normalized keyword (`only`: just these keys); labels come later."""
    element = func.jsonb_array_elements_text(F.technology_keys).table_valued("value").lateral("kw")
    statement = (
        select(element.c.value, func.count(func.distinct(F.item_id)))
        .select_from(facts.facts)
        .join(element, true())
        .where(*conditions)
        .group_by(element.c.value)
    )
    if only is not None:
        statement = statement.where(element.c.value.in_(only))
    return {str(key): int(count) for key, count in session.execute(statement).tuples() if key}


def insights(session: Session, filters: ReaderFilters, window: Window) -> Insights:
    chosen = facts.conditions(filters)
    current = [*chosen, *facts.in_window(window)]
    previous_window = window.previous() if window.start is not None else None
    previous = [*chosen, *facts.in_window(previous_window)] if previous_window else None

    columns = {"fields": F.field, "signal_types": F.signal_type, "impacts": F.impact}
    split: dict[str, dict[str, int]] = {name: {} for name in columns}
    total = 0
    statement = (
        select(*(func.grouping(c) for c in columns.values()), *columns.values(), func.count())
        .where(*current)
        .group_by(func.grouping_sets(*columns.values(), tuple_()))
    )
    width = len(columns)
    for row in session.execute(statement):
        flags, values, count = row[:width], row[width : 2 * width], int(row[-1])
        if all(flags):
            total = count
            continue
        for index, name in enumerate(columns):
            if flags[index] == 0 and values[index] is not None:
                split[name][str(values[index])] = count

    now_keywords = keyword_counts(session, current)
    ranked = sorted(now_keywords.items(), key=lambda pair: (-pair[1], pair[0]))
    top = [(key, count) for key, count in ranked if count >= KEYWORD_MIN_COUNT][:KEYWORD_TOP]
    top_keys = {key for key, _ in top}
    related = [key for key, _ in ranked if key not in top_keys][:RELATED_TOP]
    # the previous window only matters for the keys shown with a trend
    before = keyword_counts(session, previous, top_keys) if previous and top_keys else {}
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

    previous_total = (
        session.scalar(select(func.count()).select_from(facts.facts).where(*previous)) or 0
        if previous is not None
        else None
    )
    return Insights(
        total=total,
        previous_total=previous_total,
        keywords=[trend(key, labels[key], count) for key, count in top],
        related_keywords=[labels[key] for key in related],
        fields=counts(split["fields"]),
        signal_types=counts(split["signal_types"]),
        impacts=counts(split["impacts"]),
    )
