"""Radar: categories (fields), themes and technologies (card keywords) over calendar windows.

Every dimension is counted per window for the last TREND_WINDOWS windows in one query, then scored
against the earlier windows: change vs the previous window, z-score vs the baseline, a lifecycle
state, and the track mix (research + open source vs news + community) as a maturity proxy.
DX businesses are a filter here, not an axis. Counted live; R3 rollups will replace the queries.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from statistics import fmean, pstdev
from typing import Any

from sqlalchemy import ColumnElement, case, distinct, exists, func, literal, null, select, true
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.public.aggregates import KEYWORD_MIN_COUNT
from news_insight.public.feed import feed
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.periods import Window, trailing_windows
from news_insight.public.schemas import (
    Count,
    KeywordCount,
    KeywordPair,
    Radar,
    RadarKpis,
    RadarWindow,
    Topic,
    TopicDetail,
)
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem

TREND_WINDOWS = 8
MIN_SOURCES = 2  # new / surging needs more than one outlet
SURGE_Z = 2.0
KEYWORD_TOP = 90
KEYWORD_FALLING_TOP = 12
PAIR_POOL = 40
PAIR_TOP = 24
RESEARCH = (Track.RESEARCH_IP, Track.OSS)
IMPACTS = ("opportunity", "risk", "watch")
KINDS = ("field", "theme", "keyword")


def _normalized(value: Any) -> Any:
    return func.lower(func.replace(value, " ", ""))


def _bucket(windows: list[Window]) -> Any:
    """Index of the window an item falls in (rows are already limited to the whole span)."""
    if len(windows) == 1:
        return literal(0)
    return case(
        *((Item.first_seen_at < w.end, i) for i, w in enumerate(windows[:-1])),
        else_=len(windows) - 1,
    )


def _span(windows: list[Window]) -> list[ColumnElement[bool]]:
    assert windows[0].start is not None
    return [Item.first_seen_at >= windows[0].start, Item.first_seen_at < windows[-1].end]


@dataclass
class Series:
    label: str | None
    field: str | None
    counts: list[int]
    sources: int
    tracks: dict[str, int]
    previous_tracks: dict[str, int]
    impacts: dict[str, int]


def _series(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    dimension: str,
    *,
    only: str | None = None,
    min_total: int = 1,
) -> dict[str, Series]:
    """Per-window item counts for every key of one dimension, plus current-window breakdowns."""
    last = len(windows) - 1
    bucket = _bucket(windows)
    items = func.count(distinct(Item.id))
    label: Any = None
    if dimension == "field":
        key: Any = ItemCard.field
        join = None
    else:
        column = ItemCard.themes if dimension == "theme" else ItemCard.keywords
        join = func.jsonb_array_elements_text(column).table_valued("value").lateral("element")
        key = join.c.value if dimension == "theme" else _normalized(join.c.value)
        if dimension == "keyword":
            label = func.mode().within_group(join.c.value)
    columns = [
        key,
        label if label is not None else null(),
        func.mode().within_group(ItemCard.field),
        *(items.filter(bucket == i) for i in range(len(windows))),
        func.count(distinct(Item.source_id)).filter(bucket == last),
        *(items.filter(bucket == last, Item.track == t) for t in Track),
        *(items.filter(bucket == last - 1, Item.track == t) for t in Track),
        *(items.filter(bucket == last, ItemCard.impact == impact) for impact in IMPACTS),
    ]
    statement = joined(select(*columns))
    if join is not None:
        statement = statement.join(join, true())
    statement = statement.where(*conditions, *_span(windows), key.is_not(None), key != "")
    if only is not None:
        statement = statement.where(key == only)
    statement = statement.group_by(key).having(items >= min_total)
    tracks = [t.value for t in Track]
    n, k = len(windows), len(tracks)
    result: dict[str, Series] = {}
    for row in session.execute(statement).tuples():
        value, name, field, *numbers = row
        counts = [int(c) for c in numbers[:n]]
        rest = [int(c) for c in numbers[n:]]
        result[str(value)] = Series(
            label=str(name) if name is not None else None,
            field=str(field) if field is not None else None,
            counts=counts,
            sources=rest[0],
            tracks=dict(zip(tracks, rest[1 : 1 + k], strict=True)),
            previous_tracks=dict(zip(tracks, rest[1 + k : 1 + 2 * k], strict=True)),
            impacts=dict(zip(IMPACTS, rest[1 + 2 * k :], strict=True)),
        )
    return result


def change(count: int, previous: int) -> float | None:
    return round((count - previous) / previous * 100, 1) if previous else None


def z_score(counts: list[int]) -> float:
    """Current window against the earlier ones; the deviation floor of 1 damps tiny baselines."""
    *history, current = counts
    return round((current - fmean(history)) / max(pstdev(history), 1.0), 2)


def lifecycle(counts: list[int], sources: int) -> str | None:
    """new → surging → rising → steady → falling, or None when too quiet to call."""
    *history, current = counts
    mean = fmean(history)
    if current >= KEYWORD_MIN_COUNT:
        if sum(history) == 0:
            return "new" if sources >= MIN_SOURCES else "steady"
        if z_score(counts) >= SURGE_Z and current >= mean * 1.5 and sources >= MIN_SOURCES:
            return "surging"
        if current >= mean * 1.3:
            return "rising"
    if mean >= KEYWORD_MIN_COUNT and current <= mean * 0.7:
        return "falling"
    return "steady" if current >= KEYWORD_MIN_COUNT else None


def _topic(key: str, series: Series) -> Topic:
    return Topic(
        key=key,
        label=series.label,
        field=series.field,
        counts=series.counts,
        change=change(series.counts[-1], series.counts[-2]),
        z=z_score(series.counts),
        state=lifecycle(series.counts, series.sources),
        sources=series.sources,
        tracks=series.tracks,
        previous_tracks=series.previous_tracks,
        impacts=series.impacts,
    )


def window_out(window: Window, current_key: str, now: datetime) -> RadarWindow:
    assert window.start is not None
    is_current = window.key == current_key
    elapsed = None
    if is_current:
        span = (window.end - window.start).total_seconds()
        elapsed = round(min(max((now - window.start).total_seconds() / span, 0.0), 1.0), 3)
    return RadarWindow(
        kind=window.kind,
        key=window.key,
        start=window.start,
        end=window.end,
        prev_key=window.prev_key,
        next_key=window.next_key,
        is_current=is_current,
        elapsed=elapsed,
    )


def _kpis(
    session: Session, conditions: list[ColumnElement[bool]], windows: list[Window]
) -> RadarKpis:
    bucket = _bucket(windows).label("bucket")
    rows = session.execute(
        joined(
            select(
                bucket,
                func.count(distinct(Item.id)),
                func.count(distinct(func.coalesce(StoryItem.story_id, -Item.id))),
                func.count(distinct(Item.source_id)),
                func.count(distinct(Item.id)).filter(Item.track.in_(RESEARCH)),
            )
        )
        .where(*conditions, *_span(windows))
        .group_by(bucket)
    ).tuples()
    by_bucket = {int(b): (int(i), int(s), int(src), int(r)) for b, i, s, src, r in rows}
    empty = (0, 0, 0, 0)
    values = [by_bucket.get(i, empty) for i in range(len(windows))]
    current = windows[-1]
    assert current.start is not None
    stories = list(
        session.execute(
            joined(select(Story.id, func.jsonb_array_length(Story.tracks)))
            .where(
                *conditions,
                *_span([current]),
                StoryItem.story_id.is_not(None),
                Story.first_seen_at >= current.start,
                Story.first_seen_at < current.end,
            )
            .distinct()
        ).tuples()
    )
    return RadarKpis(
        items=[v[0] for v in values],
        stories=[v[1] for v in values],
        sources=[v[2] for v in values],
        research=[v[3] for v in values],
        new_stories=len(stories),
        cross_track_stories=sum(1 for _, tracks in stories if tracks >= 2),
    )


def _keyword_items(
    session: Session, conditions: list[ColumnElement[bool]], windows: list[Window], keys: set[str]
) -> dict[int, tuple[int, set[str]]]:
    """item id → (window index, its keywords among `keys`)."""
    element = func.jsonb_array_elements_text(ItemCard.keywords).table_valued("value").lateral("kw")
    normalized = _normalized(element.c.value)
    rows = session.execute(
        joined(select(Item.id, _bucket(windows), normalized))
        .join(element, true())
        .where(*conditions, *_span(windows), normalized.in_(keys))
        .distinct()
    ).tuples()
    result: dict[int, tuple[int, set[str]]] = {}
    for item_id, index, key in rows:
        result.setdefault(int(item_id), (int(index), set()))[1].add(str(key))
    return result


def _pairs(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    keywords: list[Topic],
    total: int,
) -> list[KeywordPair]:
    """Keywords named together in the current window; lift > 1 means more than chance."""
    pool = {k.key: k.counts[-1] for k in keywords if k.counts[-1] >= KEYWORD_MIN_COUNT}
    pool = dict(sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))[:PAIR_POOL])
    if len(pool) < 2 or not total:
        return []
    last = len(windows) - 1
    now: Counter[tuple[str, str]] = Counter()
    before: Counter[tuple[str, str]] = Counter()
    for index, keys in _keyword_items(session, conditions, windows, set(pool)).values():
        for pair in combinations(sorted(keys), 2):
            (now if index == last else before)[pair] += 1
    pairs = [
        KeywordPair(
            a=a,
            b=b,
            count=count,
            lift=round(count * total / (pool[a] * pool[b]), 2),
            is_new=before[(a, b)] == 0,
        )
        for (a, b), count in now.items()
        if count >= KEYWORD_MIN_COUNT
    ]
    pairs.sort(key=lambda p: (-p.count, -p.lift, p.a, p.b))
    return pairs[:PAIR_TOP]


def _pick_keywords(topics: list[Topic]) -> list[Topic]:
    called = [t for t in topics if t.state is not None]
    live = sorted(
        (t for t in called if t.state != "falling"), key=lambda t: (-t.counts[-1], -t.z, t.key)
    )
    falling = sorted(
        (t for t in called if t.state == "falling"), key=lambda t: (-fmean(t.counts[:-1]), t.key)
    )
    return live[:KEYWORD_TOP] + falling[:KEYWORD_FALLING_TOP]


def radar(
    session: Session, filters: ReaderFilters, window: Window, current_key: str, now: datetime
) -> Radar:
    base = filters.conditions()
    windows = trailing_windows(window, TREND_WINDOWS)
    kpis = _kpis(session, base, windows)

    def topics(dimension: str, min_total: int = 1) -> list[Topic]:
        series = _series(session, base, windows, dimension, min_total=min_total)
        return sorted(
            (_topic(key, s) for key, s in series.items()),
            key=lambda t: (-t.counts[-1], -sum(t.counts), t.key),
        )

    keywords = _pick_keywords(topics("keyword", min_total=KEYWORD_MIN_COUNT))
    return Radar(
        window=window_out(window, current_key, now),
        periods=[w.key for w in windows],
        kpis=kpis,
        fields=topics("field"),
        themes=topics("theme"),
        keywords=keywords,
        pairs=_pairs(session, base, windows, keywords, kpis.items[-1]),
    )


def topic_condition(kind: str, value: str) -> ColumnElement[bool]:
    if kind == "field":
        return ItemCard.field == value
    if kind == "theme":
        return ItemCard.themes.contains([value])
    element = func.jsonb_array_elements_text(ItemCard.keywords).table_valued("value").alias("k")
    return exists(select(1).select_from(element).where(_normalized(element.c.value) == value))


def _counts(session: Session, conditions: list[ColumnElement[bool]], axis: str) -> list[Count]:
    if axis == "region":
        key: Any = Source.region
        statement = joined(select(key, func.count(distinct(Item.id))))
    else:
        column = ItemCard.themes if axis == "theme" else ItemCard.businesses
        element = func.jsonb_array_elements_text(column).table_valued("value").lateral(axis)
        key = element.c.value
        statement = joined(select(key, func.count(distinct(Item.id)))).join(element, true())
    rows = session.execute(statement.where(*conditions).group_by(key)).tuples()
    return [
        Count(key=str(k), count=int(c))
        for k, c in sorted(rows, key=lambda pair: (-int(pair[1]), str(pair[0])))
    ]


def topic_detail(
    session: Session, filters: ReaderFilters, window: Window, *, kind: str, value: str
) -> TopicDetail:
    condition = topic_condition(kind, value)
    base = [*filters.conditions(), condition]
    windows = trailing_windows(window, TREND_WINDOWS)
    series = _series(session, base, windows, kind, only=value).get(value)
    counts = series.counts if series else [0] * TREND_WINDOWS
    empty = dict.fromkeys((t.value for t in Track), 0)
    topic = (
        _topic(value, series)
        if series
        else Topic(
            key=value,
            label=None,
            field=None,
            counts=counts,
            change=None,
            z=0.0,
            state=None,
            sources=0,
            tracks=empty,
            previous_tracks=empty,
            impacts=dict.fromkeys(IMPACTS, 0),
        )
    )
    current = [*base, *_span([window])]
    related = _series(session, base, [window], "keyword")
    related.pop(value, None)
    keywords = sorted(related.items(), key=lambda kv: (-kv[1].counts[-1], kv[0]))[:12]
    stories = feed(session, filters, window, sort="coverage", page=1, size=5, extra=[condition])
    return TopicDetail(
        kind=kind,
        topic=topic,
        themes=[c for c in _counts(session, current, "theme") if c.key != value][:8],
        keywords=[
            KeywordCount(key=key, label=s.label or key, count=s.counts[-1]) for key, s in keywords
        ],
        businesses=_counts(session, current, "business"),
        regions=_counts(session, current, "region"),
        stories=stories.items,
    )
