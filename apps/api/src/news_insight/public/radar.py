"""Radar: field × DX business heatmap, momentum, chatter-vs-research and keyword shifts.

Everything is counted live per calendar window; R3 rollups will replace the queries, not the shape.
"""

from sqlalchemy import ColumnElement, func, select, true
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.public.aggregates import KEYWORD_MIN_COUNT, keyword_counts
from news_insight.public.feed import feed
from news_insight.public.filters import ReaderFilters, in_window, joined
from news_insight.public.periods import Window, trailing_windows
from news_insight.public.schemas import (
    Cell,
    CellDetail,
    Count,
    FieldMomentum,
    HotCell,
    HypePoint,
    KeywordCount,
    KeywordShift,
    Radar,
    RadarKpis,
    RadarWindow,
)
from news_insight.sources.enums import Track
from news_insight.stories.models import Story, StoryItem

NO_BUSINESS = "none"
TREND_WINDOWS = 8
SHIFT_HISTORY = 4
SHIFT_TOP = 6
CHATTER = (Track.NEWS, Track.COMMUNITY)
RESEARCH = (Track.RESEARCH_IP, Track.OSS)


def _change(count: int, previous: int) -> float | None:
    return round((count - previous) / previous * 100, 1) if previous else None


def _cells(session: Session, conditions: list[ColumnElement[bool]]) -> dict[tuple[str, str], int]:
    element = func.jsonb_array_elements_text(ItemCard.businesses).table_valued("value").lateral("b")
    business = func.coalesce(element.c.value, NO_BUSINESS)
    statement = (
        joined(select(ItemCard.field, business, func.count(func.distinct(Item.id))))
        .outerjoin(element, true())
        .where(*conditions, ItemCard.field.is_not(None))
        .group_by(ItemCard.field, business)
    )
    return {
        (str(field), str(key)): int(count)
        for field, key, count in session.execute(statement).tuples()
    }


def _by_field(
    session: Session, conditions: list[ColumnElement[bool]], *extra: ColumnElement[bool]
) -> dict[str, int]:
    statement = (
        joined(select(ItemCard.field, func.count(func.distinct(Item.id))))
        .where(*conditions, *extra, ItemCard.field.is_not(None))
        .group_by(ItemCard.field)
    )
    return {str(field): int(count) for field, count in session.execute(statement).tuples()}


def _count(session: Session, conditions: list[ColumnElement[bool]]) -> int:
    return (
        session.scalar(joined(select(func.count(func.distinct(Item.id)))).where(*conditions)) or 0
    )


def _stories(
    session: Session, conditions: list[ColumnElement[bool]], window: Window
) -> tuple[int, int]:
    assert window.start is not None
    statement = (
        joined(select(Story.id, func.jsonb_array_length(Story.tracks)))
        .where(
            *conditions,
            StoryItem.story_id.is_not(None),
            Story.first_seen_at >= window.start,
            Story.first_seen_at < window.end,
        )
        .distinct()
    )
    rows = list(session.execute(statement).tuples())
    return len(rows), sum(1 for _, tracks in rows if tracks >= 2)


def window_out(window: Window, current_key: str) -> RadarWindow:
    assert window.start is not None
    return RadarWindow(
        kind=window.kind,
        key=window.key,
        start=window.start,
        end=window.end,
        prev_key=window.prev_key,
        next_key=window.next_key,
        is_current=window.key == current_key,
    )


def _shift_state(counts: list[int]) -> str | None:
    *history, current = counts
    average = sum(history) / len(history)
    if current >= KEYWORD_MIN_COUNT and sum(history) == 0:
        return "new"
    if current >= KEYWORD_MIN_COUNT and current >= average * 1.3:
        return "rising"
    if average >= KEYWORD_MIN_COUNT and current <= average * 0.7:
        return "falling"
    if current >= KEYWORD_MIN_COUNT:
        return "steady"
    return None


def radar(session: Session, filters: ReaderFilters, window: Window, current_key: str) -> Radar:
    base = filters.conditions()
    previous = window.previous()
    now_cells = _cells(session, [*base, *in_window(window)])
    before_cells = _cells(session, [*base, *in_window(previous)])
    cells = [
        Cell(
            field=field,
            business=business,
            count=now_cells.get(key, 0),
            previous=before_cells.get(key, 0),
        )
        for key in sorted(now_cells.keys() | before_cells.keys())
        for field, business in [key]
    ]
    hot = sorted(
        (cell for cell in cells if cell.count >= KEYWORD_MIN_COUNT),
        key=lambda c: (-(c.count - c.previous) / max(c.previous, 1), -c.count, c.field, c.business),
    )
    new_stories, cross_track = _stories(session, [*base, *in_window(window)], window)

    windows = trailing_windows(window, TREND_WINDOWS)
    series = [_by_field(session, [*base, *in_window(w)]) for w in windows]
    fields = sorted(
        {field for counts in series for field in counts},
        key=lambda field: (-series[-1].get(field, 0), field),
    )
    momentum = [
        FieldMomentum(
            key=field,
            counts=[counts.get(field, 0) for counts in series],
            change=_change(series[-1].get(field, 0), series[-2].get(field, 0)),
        )
        for field in fields
    ]

    def by_tracks(w: Window, tracks: tuple[Track, ...]) -> dict[str, int]:
        return _by_field(session, [*base, *in_window(w)], Item.track.in_(tracks))

    chatter, chatter_before = by_tracks(window, CHATTER), by_tracks(previous, CHATTER)
    research, research_before = by_tracks(window, RESEARCH), by_tracks(previous, RESEARCH)
    hype = [
        HypePoint(
            key=field,
            chatter=chatter.get(field, 0),
            chatter_change=_change(chatter.get(field, 0), chatter_before.get(field, 0)),
            research=research.get(field, 0),
            research_change=_change(research.get(field, 0), research_before.get(field, 0)),
        )
        for field in sorted(
            chatter.keys() | chatter_before.keys() | research.keys() | research_before.keys()
        )
    ]

    history = trailing_windows(window, SHIFT_HISTORY + 1)
    keyword_series = [keyword_counts(session, [*base, *in_window(w)]) for w in history]
    labels = {key: label for counts in keyword_series for key, (label, _) in counts.items()}
    shifts: list[KeywordShift] = []
    for key in sorted(labels):
        counts = [counts.get(key, ("", 0))[1] for counts in keyword_series]
        state = _shift_state(counts)
        if state is not None:
            shifts.append(KeywordShift(key=key, label=labels[key], state=state, counts=counts))
    shifts.sort(key=lambda s: (-s.counts[-1], s.key))
    per_state: dict[str, int] = {}
    keywords = []
    for shift in shifts:
        if per_state.get(shift.state, 0) < SHIFT_TOP:
            per_state[shift.state] = per_state.get(shift.state, 0) + 1
            keywords.append(shift)

    return Radar(
        window=window_out(window, current_key),
        kpis=RadarKpis(
            total=_count(session, [*base, *in_window(window)]),
            previous_total=_count(session, [*base, *in_window(previous)]),
            new_stories=new_stories,
            cross_track_stories=cross_track,
            hottest=HotCell(
                field=hot[0].field,
                business=hot[0].business,
                count=hot[0].count,
                previous=hot[0].previous,
            )
            if hot
            else None,
        ),
        cells=cells,
        momentum=momentum,
        hype=hype,
        keywords=keywords,
    )


def cell_detail(
    session: Session, filters: ReaderFilters, window: Window, *, field: str, business: str
) -> CellDetail:
    extra: list[ColumnElement[bool]] = [ItemCard.field == field]
    if business == NO_BUSINESS:
        extra.append(func.jsonb_array_length(ItemCard.businesses) == 0)
    else:
        extra.append(ItemCard.businesses.contains([business]))
    base = [*filters.conditions(), *extra]
    trend = [
        _count(session, [*base, *in_window(w)]) for w in trailing_windows(window, TREND_WINDOWS)
    ]
    current = [*base, *in_window(window)]
    element = func.jsonb_array_elements_text(ItemCard.themes).table_valued("value").lateral("t")
    themes = session.execute(
        joined(select(element.c.value, func.count(func.distinct(Item.id))))
        .join(element, true())
        .where(*current)
        .group_by(element.c.value)
    ).tuples()
    keywords = sorted(
        keyword_counts(session, current).items(), key=lambda pair: (-pair[1][1], pair[0])
    )
    stories = feed(session, filters, window, sort="coverage", page=1, size=4, extra=extra)
    return CellDetail(
        field=field,
        business=business,
        count=trend[-1],
        previous=trend[-2],
        trend=trend,
        themes=[
            Count(key=str(key), count=int(count))
            for key, count in sorted(themes, key=lambda pair: (-pair[1], pair[0]))
        ],
        keywords=[
            KeywordCount(key=key, label=label, count=count) for key, (label, count) in keywords[:8]
        ],
        stories=stories.items,
    )
