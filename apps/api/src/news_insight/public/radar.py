"""Radar: categories (fields), themes and technologies (card keywords) over calendar windows.

Every dimension is counted per window for the last TREND_WINDOWS windows in one query, then scored
against the earlier windows: change vs the previous window, z-score vs the baseline, a lifecycle
state, and the track mix (research + open source vs news + community) as a maturity proxy.
Signal types (research, launch, regulation, …) are a filter here, not an axis.
Counted live; R3 rollups will replace the queries.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import combinations
from math import log1p
from statistics import fmean, median
from typing import Any

from sqlalchemy import ColumnElement, case, distinct, func, literal, null, select, true
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import info_for
from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.public.aggregates import KEYWORD_MIN_COUNT
from news_insight.public.feed import feed
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.keywords import company_element, keyword_element
from news_insight.public.periods import KST, Window, trailing_windows
from news_insight.public.schemas import (
    Anomaly,
    Calendar,
    CompanyProfile,
    CompanyRef,
    Count,
    EngagedItem,
    Engagement,
    FieldLink,
    FlowLink,
    Flows,
    KeywordCount,
    KeywordPair,
    Radar,
    RadarKpis,
    RadarWindow,
    ThemeEngagement,
    Topic,
    TopicDetail,
)
from news_insight.public.signals import radar_signals
from news_insight.public.stats import count_z, rate_z
from news_insight.sources.enums import Region, Track
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef, Story, StoryItem
from news_insight.taxonomy.catalog import TAXONOMY_REVISED_ON
from news_insight.technologies.service import labels_for

TREND_WINDOWS = 8
MIN_SOURCES = 2  # new / surging needs more than one outlet
SURGE_Z = 2.0
SURGE_MOVE = 1.5  # and at least this many times the baseline mean
RISE_Z = 1.0
FALL_Z = -1.0
KEYWORD_TOP = 90
KEYWORD_FALLING_TOP = 12
PAIR_POOL = 40
PAIR_TOP = 24
RESEARCH = (Track.RESEARCH_IP, Track.OSS)
IMPACTS = ("opportunity", "risk", "watch")
KINDS = ("field", "theme", "keyword", "company")
OFFICIAL = "official_vendor"
# ties between tracks reached at the same moment go research-first
PIPELINE = (Track.RESEARCH_IP, Track.OSS, Track.COMMUNITY, Track.NEWS)
TRACK_ORDER = {t.value: i for i, t in enumerate(PIPELINE)}
# reactions that grow over time; anything else in item metrics (views, rank) is ignored
REACTIONS = ("stars", "points", "likes", "reactions", "score", "comments", "downloads", "answers")
ENGAGED_TOP = 8
CALENDAR_DAYS = (84, 371)  # at least 12 weeks of context, at most a year
ANOMALY_BASELINE = 28
ANOMALY_Z = 3.0
ANOMALY_RATIO = 2.5  # and at least this many times the usual level
ANOMALY_MIN = 8  # a handful of reports in a quiet category is noise, not an event
DEBUT_WINDOWS = 3
ANOMALY_TOP = 8


def _bucket(windows: list[Window]) -> Any:
    """Index of the window an item falls in (rows are already limited to the whole span)."""
    if len(windows) == 1:
        return literal(0)
    return case(
        *((Item.first_seen_at < w.end, i) for i, w in enumerate(windows[:-1])),
        else_=len(windows) - 1,
    )


def paced_cutoffs(windows: list[Window], now: datetime) -> list[datetime] | None:
    """For a window still in progress: each window's start plus the same elapsed share, so earlier
    windows are compared up to the same point (same weekday and hour for weeks; checklist STAT-2).
    None for a closed window."""
    current = windows[-1]
    assert current.start is not None
    if not current.start <= now < current.end:
        return None
    share = (now - current.start) / (current.end - current.start)
    cutoffs = []
    for w in windows:
        assert w.start is not None
        cutoffs.append(w.start + (w.end - w.start) * share)
    return cutoffs


def _paced(windows: list[Window], cutoffs: list[datetime] | None) -> ColumnElement[bool]:
    """Item falls before its window's paced cutoff (always true without cutoffs)."""
    if cutoffs is None:
        return true()
    bucket = _bucket(windows)
    return Item.first_seen_at < case(
        *((bucket == i, literal(c)) for i, c in enumerate(cutoffs[:-1])), else_=literal(cutoffs[-1])
    )


def _span(windows: list[Window]) -> list[ColumnElement[bool]]:
    assert windows[0].start is not None
    return [Item.first_seen_at >= windows[0].start, Item.first_seen_at < windows[-1].end]


def _dimension(dimension: str) -> tuple[Any, Any, Any]:
    """(key expression, lateral join or None, display label or None) for one dimension."""
    if dimension == "field":
        return ItemCard.field, None, None
    if dimension == "theme":
        join = (
            func.jsonb_array_elements_text(ItemCard.themes).table_valued("value").lateral("element")
        )
        return join.c.value, join, None
    if dimension == "company":
        join = company_element("element")
        return join.c.value, join, None  # names come from the registry after grouping
    join = keyword_element("element")
    return join.c.value, join, None  # labels are looked up once after grouping


@dataclass
class Series:
    label: str | None
    field: str | None
    counts: list[int]
    sources: int
    tracks: dict[str, int]
    previous_tracks: dict[str, int]
    baseline_tracks: dict[str, int]
    impacts: dict[str, int]
    regions: dict[str, int]
    first_seen: dict[str, datetime]
    official: int
    paced: list[int] | None = None  # counts up to the same elapsed share (window in progress)


def _series(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    dimension: str,
    *,
    only: str | None = None,
    min_total: int = 1,
    cutoffs: list[datetime] | None = None,
) -> dict[str, Series]:
    """Per-window item counts for every key of one dimension, plus current-window breakdowns.

    With `cutoffs` (a window in progress) the earlier windows' track breakdowns and a second set
    of counts stop at the same elapsed share, so they compare like with like.
    """
    last = len(windows) - 1
    bucket = _bucket(windows)
    paced = _paced(windows, cutoffs)
    # one row per item and key: a card per item, a story per item (story_items.item_id is the
    # primary key), and themes, keyword keys and company keys are de-duplicated when written,
    # so count(*) equals count(DISTINCT item) without sorting ~60 aggregates (2026-10-05: the
    # keyword series took 2.6 s of a 6.7 s radar)
    items = func.count()
    key, join, label = _dimension(dimension)
    n_paced = len(windows) if cutoffs is not None else 0
    columns = [
        key,
        label if label is not None else null(),
        func.mode().within_group(ItemCard.field),
        *(items.filter(bucket == i) for i in range(len(windows))),
        *(items.filter(bucket == i, paced) for i in range(n_paced)),
        func.count(distinct(Item.source_id)).filter(bucket == last),
        *(items.filter(bucket == last, Item.track == t) for t in Track),
        *(items.filter(bucket == last - 1, Item.track == t, paced) for t in Track),
        *(items.filter(bucket < last, Item.track == t, paced) for t in Track),
        *(items.filter(bucket == last, ItemCard.impact == impact) for impact in IMPACTS),
        *(items.filter(bucket == last, Source.region == r) for r in Region),
        items.filter(bucket == last, Source.category == OFFICIAL),
        *(func.min(Item.first_seen_at).filter(Source.region == r) for r in Region),
    ]
    statement = joined(select(*columns))
    if join is not None:
        statement = statement.join(join, true())
    statement = statement.where(*conditions, *_span(windows), key.is_not(None), key != "")
    if only is not None:
        statement = statement.where(key == only)
    statement = statement.group_by(key).having(items >= min_total)
    tracks = [t.value for t in Track]
    regions = [r.value for r in Region]
    n, k, m = len(windows), len(tracks), len(regions)
    result: dict[str, Series] = {}
    for row in session.execute(statement).tuples():
        value, name, field, *numbers = row
        firsts = numbers[-m:]
        counts = [int(c) for c in numbers[:n]]
        paced_counts = [int(c) for c in numbers[n : n + n_paced]] or None
        rest = [int(c) for c in numbers[n + n_paced : -m]]
        at = 1 + 3 * k + len(IMPACTS)
        result[str(value)] = Series(
            label=str(name) if name is not None else None,
            field=str(field) if field is not None else None,
            counts=counts,
            sources=rest[0],
            tracks=dict(zip(tracks, rest[1 : 1 + k], strict=True)),
            previous_tracks=dict(zip(tracks, rest[1 + k : 1 + 2 * k], strict=True)),
            baseline_tracks=dict(zip(tracks, rest[1 + 2 * k : 1 + 3 * k], strict=True)),
            impacts=dict(zip(IMPACTS, rest[1 + 3 * k : at], strict=True)),
            regions=dict(zip(regions, rest[at : at + m], strict=True)),
            official=rest[at + m],
            first_seen={r: t for r, t in zip(regions, firsts, strict=True) if t is not None},
            paced=paced_counts,
        )
    if dimension == "keyword":
        for key_value, label in labels_for(session, result).items():
            result[key_value].label = label
    if dimension == "company":
        for key_value, info in info_for(session, result).items():
            result[key_value].label = info.name_ko or info.name
    return result


SOURCE_DAY_CAP = 3  # reports one source can add to a topic per day (checklist STAT-1)


@dataclass(frozen=True)
class SourceMix:
    """Current-window source structure of one topic."""

    effective: float  # 1 / HHI of reports per source: 1 = one outlet, n = n equal
    capped: dict[str, int]  # reports per track, at most SOURCE_DAY_CAP per source and day


def _capped_rows(
    session: Session, conditions: list[ColumnElement[bool]], window: Window, dimension: str | None
) -> list[tuple[str | None, int, str, int]]:
    """(key, source, track, reports) per source and KST day in the window."""
    day = _kst_day(Item.first_seen_at)
    if dimension is None:
        statement = joined(
            select(null(), Item.source_id, Item.track, func.count(distinct(Item.id)))
        ).where(*conditions, *_span([window]))
        group: tuple[Any, ...] = (Item.source_id, Item.track, day)
    else:
        key, join, _ = _dimension(dimension)
        statement = joined(select(key, Item.source_id, Item.track, func.count(distinct(Item.id))))
        if join is not None:
            statement = statement.join(join, true())
        statement = statement.where(*conditions, *_span([window]), key.is_not(None))
        group = (key, Item.source_id, Item.track, day)
    return [
        (None if k is None else str(k), int(source), Track(track).value, int(count))
        for k, source, track, count in session.execute(statement.group_by(*group)).tuples()
    ]


def _source_mix(
    session: Session, conditions: list[ColumnElement[bool]], window: Window, dimension: str
) -> dict[str, SourceMix]:
    per_source: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    capped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for key, source, track, count in _capped_rows(session, conditions, window, dimension):
        assert key is not None
        per_source[key][source] += count
        capped[key][track] += min(count, SOURCE_DAY_CAP)
    return {
        key: SourceMix(
            effective=round(sum(c.values()) ** 2 / sum(v * v for v in c.values()), 2),
            capped=dict(capped[key]),
        )
        for key, c in per_source.items()
    }


def _track_totals(
    session: Session, conditions: list[ColumnElement[bool]], window: Window
) -> dict[str, int]:
    """Capped reports per track in the window: the denominators of the normalised share."""
    totals: dict[str, int] = defaultdict(int)
    for _, _, track, count in _capped_rows(session, conditions, window, None):
        totals[track] += min(count, SOURCE_DAY_CAP)
    return dict(totals)


def normalized_share(capped: dict[str, int], totals: dict[str, int]) -> float | None:
    """Mean of the topic's share within each track (percent). Every track weighs the same, so
    adding news or community sources does not inflate topics those tracks favour."""
    shares = [capped.get(track, 0) / total for track, total in totals.items() if total]
    return round(sum(shares) / len(shares) * 100, 2) if shares else None


def change(count: int, previous: int) -> float | None:
    return round((count - previous) / previous * 100, 1) if previous else None


def z_score(counts: list[int]) -> float:
    """Current window against the earlier ones (overdispersed Poisson z, public/stats.py)."""
    *history, current = counts
    return round(count_z(current, history), 2)


def lifecycle(counts: list[int], sources: int, *, seen_before: bool | None = None) -> str | None:
    """new → surging → rising → steady → falling, or None when too quiet to call.

    `seen_before` overrides "any earlier count" for paced counts, where a report late in an
    earlier window is cut off but still means the topic is not new."""
    *history, current = counts
    mean = fmean(history)
    if current >= KEYWORD_MIN_COUNT:
        if not (sum(history) > 0 if seen_before is None else seen_before):
            return "new" if sources >= MIN_SOURCES else "steady"
        z = z_score(counts)
        if z >= SURGE_Z and current >= mean * SURGE_MOVE and sources >= MIN_SOURCES:
            return "surging"
        if z >= RISE_Z:
            return "rising"
    if mean >= KEYWORD_MIN_COUNT and z_score(counts) <= FALL_Z:
        return "falling"
    return "steady" if current >= KEYWORD_MIN_COUNT else None


def _topic(
    key: str, series: Series, mix: SourceMix | None = None, totals: dict[str, int] | None = None
) -> Topic:
    scored = series.paced or series.counts
    return Topic(
        key=key,
        label=series.label,
        field=series.field,
        counts=series.counts,
        paced=series.paced,
        change=change(scored[-1], scored[-2]),
        z=z_score(scored),
        state=lifecycle(scored, series.sources, seen_before=sum(series.counts[:-1]) > 0),
        sources=series.sources,
        tracks=series.tracks,
        previous_tracks=series.previous_tracks,
        baseline_tracks=series.baseline_tracks,
        impacts=series.impacts,
        regions=series.regions,
        first_seen=series.first_seen,
        official=series.official,
        effective_sources=mix.effective if mix else None,
        capped=sum(mix.capped.values()) if mix else 0,
        normalized_share=normalized_share(mix.capped, totals) if mix and totals else None,
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
    element = keyword_element("kw")
    normalized = element.c.value
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


def _arrivals(
    session: Session,
    chain: Any,
    conditions: list[ColumnElement[bool]],
    window: Window,
    *,
    refs: bool = False,
) -> dict[str, dict[str, datetime]]:
    """chain key → track → first time that track reported on it (up to the window end)."""
    statement = joined(select(chain, Item.track, func.min(Item.first_seen_at)))
    if refs:
        statement = statement.join(ItemRef, ItemRef.item_id == Item.id)
    rows = session.execute(
        statement.where(*conditions, chain.is_not(None), Item.first_seen_at < window.end).group_by(
            chain, Item.track
        )
    ).tuples()
    result: dict[str, dict[str, datetime]] = defaultdict(dict)
    for key, track, at in rows:
        result[str(key)][Track(track).value] = at
    return result


def _flows(session: Session, conditions: list[ColumnElement[bool]], window: Window) -> Flows:
    """How reports moved between tracks: within a story, or via a shared identifier (arXiv,
    DOI, repository, CVE, 3GPP spec, patent, Hugging Face model).

    A chain counts when one of its tracks was first reached inside the window; each step is the
    next track to pick the subject up, with the hours it took.
    """
    assert window.start is not None
    touching = [Story.last_seen_at >= window.start, Story.first_seen_at < window.end]
    stories = _arrivals(session, StoryItem.story_id, [*conditions, *touching], window)
    ref = func.concat(ItemRef.kind, ":", ItemRef.value)
    refs = _arrivals(session, ref, conditions, window, refs=True)
    origins: Counter[str] = Counter()
    lags: dict[tuple[str, str], list[float]] = defaultdict(list)
    chains = 0
    ref_kinds: Counter[str] = Counter()
    chained = [(None, a) for a in stories.values()] + [(str(k), a) for k, a in refs.items()]
    for ref_key, arrivals in chained:
        if len(arrivals) < 2:
            continue
        ordered = sorted(arrivals.items(), key=lambda kv: (kv[1], TRACK_ORDER[kv[0]]))
        steps = [(a, b) for a, b in zip(ordered, ordered[1:], strict=False) if b[1] >= window.start]
        if not steps:
            continue
        chains += 1
        origins[ordered[0][0]] += 1
        if ref_key is not None:
            ref_kinds[ref_key.split(":", 1)[0]] += 1
        for (source, start), (target, end) in steps:
            lags[(source, target)].append((end - start).total_seconds() / 3600)
    links = [
        FlowLink(source=a, target=b, count=len(hours), median_hours=round(median(hours), 1))
        for (a, b), hours in lags.items()
    ]
    links.sort(key=lambda link: (-link.count, link.source, link.target))
    return Flows(chains=chains, origins=dict(origins), links=links, ref_kinds=dict(ref_kinds))


def _first_ever(
    session: Session, conditions: list[ColumnElement[bool]], keys: list[str]
) -> dict[str, datetime]:
    """First report ever for each keyword key (with the reader filters, no window)."""
    if not keys:
        return {}
    element = keyword_element("kw")
    key = element.c.value
    rows = session.execute(
        joined(select(key, func.min(Item.first_seen_at)))
        .join(element, true())
        .where(*conditions, key.in_(keys))
        .group_by(key)
    ).tuples()
    return {str(k): at for k, at in rows}


def _engagement(
    session: Session, conditions: list[ColumnElement[bool]], window: Window, themes: list[Topic]
) -> Engagement:
    """Reactions each item gained inside the window: last snapshot before the window end minus
    the last one before its start (or the first one inside it for items seen later)."""
    assert window.start is not None
    active = (
        select(ItemMetricSnapshot.item_id)
        .where(
            ItemMetricSnapshot.captured_at >= window.start,
            ItemMetricSnapshot.captured_at < window.end,
        )
        .distinct()
    )
    rows = session.execute(
        joined(
            select(
                Item.id,
                ItemMetricSnapshot.captured_at,
                ItemMetricSnapshot.metrics,
            )
        )
        .join(ItemMetricSnapshot, ItemMetricSnapshot.item_id == Item.id)
        .where(
            *conditions,
            Item.id.in_(active),
            ItemMetricSnapshot.captured_at < window.end,
            ItemMetricSnapshot.captured_at >= window.start - timedelta(days=30),
        )
        .order_by(Item.id, ItemMetricSnapshot.captured_at)
    ).tuples()
    series: dict[int, list[tuple[datetime, dict[str, Any]]]] = defaultdict(list)
    for item_id, at, metrics in rows:
        series[int(item_id)].append((at, metrics))
    gains: dict[int, dict[str, tuple[int, int]]] = {}
    for item_id, points in series.items():
        before = [m for at, m in points if at < window.start]
        inside = [m for at, m in points if at >= window.start]
        base, end = (before[-1] if before else inside[0]), inside[-1]
        grown = {}
        for name in REACTIONS:
            now, then = end.get(name), base.get(name)
            if isinstance(now, int) and isinstance(then, int) and now > then:
                grown[name] = (now - then, now)
        if grown:
            gains[item_id] = grown
    if not gains:
        return Engagement(measured=0, themes=[], top=[])
    score = {i: sum(log1p(gain) for gain, _ in g.values()) for i, g in gains.items()}
    cards = session.execute(
        select(Item.id, Item.title, ItemCard.title_ko, Item.track, Source.name, ItemCard.themes)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .join(Source, Source.id == Item.source_id)
        .where(Item.id.in_(list(gains)))
    ).tuples()
    by_theme: dict[str, list[float]] = defaultdict(list)
    top: list[EngagedItem] = []
    for item_id, title, title_ko, track, source_name, item_themes in cards:
        for theme in item_themes or []:
            by_theme[theme].append(score[item_id])
        metric, (gain, current) = max(gains[item_id].items(), key=lambda kv: kv[1][0])
        top.append(
            EngagedItem(
                id=item_id,
                title=title_ko or title,
                track=Track(track).value,
                source_name=source_name,
                metric=metric,
                gain=gain,
                current=current,
            )
        )
    top.sort(key=lambda item: (-score[item.id], item.id))
    known = {t.key for t in themes}
    return Engagement(
        measured=len(gains),
        themes=sorted(
            (
                ThemeEngagement(key=key, score=round(sum(values), 2), items=len(values))
                for key, values in by_theme.items()
                if key in known
            ),
            key=lambda t: (-t.score, t.key),
        ),
        top=top[:ENGAGED_TOP],
    )


def _kst_day(column: Any) -> Any:
    return func.date(func.timezone(str(KST), column))


def _calendar(
    session: Session, conditions: list[ColumnElement[bool]], windows: list[Window]
) -> Calendar:
    """Daily report counts ending with the window, and days when one category ran far above
    its usual level for that weekday (an announcement, a launch event, an incident)."""
    end = windows[-1].end.astimezone(KST).date()
    first = windows[0].start
    assert first is not None
    span = (end - first.astimezone(KST).date()).days
    start = end - timedelta(days=min(max(span, CALENDAR_DAYS[0]), CALENDAR_DAYS[1]))
    since = datetime.combine(start, datetime.min.time(), tzinfo=KST)
    day = _kst_day(Item.first_seen_at)
    rows = session.execute(
        joined(select(day, ItemCard.field, func.count(distinct(Item.id))))
        .where(*conditions, Item.first_seen_at >= since, Item.first_seen_at < windows[-1].end)
        .group_by(day, ItemCard.field)
    ).tuples()
    length = (end - start).days
    days = [0] * length
    by_field: dict[str, list[int]] = defaultdict(lambda: [0] * length)
    for d, field, count in rows:
        days[(d - start).days] += int(count)
        if field:
            by_field[str(field)][(d - start).days] = int(count)
    found: list[tuple[int, str, float, float]] = []
    for field, series in by_field.items():
        for i in range(ANOMALY_BASELINE, length):
            same_day = [series[j] for j in range(i - ANOMALY_BASELINE, i) if (i - j) % 7 == 0]
            expected = fmean(same_day)
            z = rate_z(series[i], expected)
            if z >= ANOMALY_Z and series[i] >= max(expected * ANOMALY_RATIO, ANOMALY_MIN):
                found.append((i, field, round(expected, 1), round(z, 2)))
    found = sorted(found, key=lambda row: -row[3])[:ANOMALY_TOP]
    anomalies = [
        Anomaly(
            day=start + timedelta(days=i),
            field=field,
            count=by_field[field][i],
            expected=expected,
            z=z,
            keywords=_spike_keywords(
                session, [*conditions, ItemCard.field == field], start + timedelta(days=i)
            ),
        )
        for i, field, expected, z in sorted(found)
    ]
    return Calendar(start=start, days=days, anomalies=anomalies)


def _spike_keywords(
    session: Session, conditions: list[ColumnElement[bool]], day: date
) -> list[KeywordCount]:
    """Keywords most above their average day over the previous four weeks."""
    element = keyword_element("kw")
    key = element.c.value
    on = _kst_day(Item.first_seen_at)
    begin = datetime.combine(day - timedelta(days=ANOMALY_BASELINE), datetime.min.time(), KST)
    finish = datetime.combine(day + timedelta(days=1), datetime.min.time(), KST)
    rows = session.execute(
        joined(
            select(
                key,
                func.count(distinct(Item.id)).filter(on == day),
                func.count(distinct(Item.id)).filter(on < day),
            )
        )
        .join(element, true())
        .where(*conditions, Item.first_seen_at >= begin, Item.first_seen_at < finish)
        .group_by(key)
    ).tuples()
    lifted = [
        (int(today) - int(before) / ANOMALY_BASELINE, str(k), int(today))
        for k, today, before in rows
        if int(today) >= KEYWORD_MIN_COUNT
    ]
    lifted.sort(key=lambda row: (-row[0], row[1]))
    labels = labels_for(session, [k for _, k, _ in lifted[:3]])
    return [KeywordCount(key=k, label=labels[k], count=count) for _, k, count in lifted[:3]]


def _field_links(
    session: Session, conditions: list[ColumnElement[bool]], windows: list[Window]
) -> list[FieldLink]:
    """Reports whose themes span two categories, this window and the one before."""
    recent = windows[-2:]
    rows = session.execute(
        joined(select(Item.id, _bucket(recent), ItemCard.field, ItemCard.themes))
        .where(*conditions, *_span(recent))
        .distinct()
    ).tuples()
    now: Counter[tuple[str, str]] = Counter()
    before: Counter[tuple[str, str]] = Counter()
    for _, index, field, item_themes in rows:
        fields = {t.split("__", 1)[0] for t in item_themes or []} | ({field} if field else set())
        for pair in combinations(sorted(fields), 2):
            (now if index == len(recent) - 1 else before)[pair] += 1
    links = [
        FieldLink(a=a, b=b, count=count, previous=before[(a, b)]) for (a, b), count in now.items()
    ]
    links.sort(key=lambda link: (-link.count, link.a, link.b))
    return links


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
    cutoffs = paced_cutoffs(windows, now)
    kpis = _kpis(session, base, windows)

    totals = _track_totals(session, base, window)

    def topics(dimension: str, min_total: int = 1) -> list[Topic]:
        series = _series(session, base, windows, dimension, min_total=min_total, cutoffs=cutoffs)
        mixes = _source_mix(session, base, window, dimension)
        return sorted(
            (_topic(key, s, mixes.get(key), totals) for key, s in series.items()),
            key=lambda t: (-t.counts[-1], -sum(t.counts), t.key),
        )

    keywords = _with_history(
        session, base, windows, _pick_keywords(topics("keyword", min_total=KEYWORD_MIN_COUNT))
    )
    themes = topics("theme")
    body = Radar(
        taxonomy_revised_on=date.fromisoformat(TAXONOMY_REVISED_ON),
        window=window_out(window, current_key, now),
        periods=[w.key for w in windows],
        kpis=kpis,
        fields=topics("field"),
        themes=themes,
        keywords=keywords,
        pairs=_pairs(session, base, windows, keywords, kpis.items[-1]),
        flows=_flows(session, base, window),
        engagement=_engagement(session, base, window, themes),
        calendar=_calendar(session, base, windows),
        field_links=_field_links(session, base, windows),
    )
    body.signals = radar_signals(body, now=now)
    return body


def _with_history(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    keywords: list[Topic],
) -> list[Topic]:
    """Add each keyword's first report ever: a "new" keyword seen before the span is returning;
    one first reported in the last DEBUT_WINDOWS windows is a debut."""
    first = _first_ever(session, conditions, [k.key for k in keywords])
    start, recent = windows[0].start, windows[-DEBUT_WINDOWS:][0].start
    assert start is not None and recent is not None
    return [
        k.model_copy(
            update={
                "first_ever": first.get(k.key),
                "returning": k.state == "new" and k.key in first and first[k.key] < start,
                "debut": k.key in first and first[k.key] >= recent,
            }
        )
        for k in keywords
    ]


def topic_condition(kind: str, value: str) -> ColumnElement[bool]:
    if kind == "field":
        return ItemCard.field == value
    if kind == "theme":
        return ItemCard.themes.contains([value])
    if kind == "company":
        return ItemCard.company_keys.contains([value])
    return ItemCard.technology_keys.contains([value])


def _counts(session: Session, conditions: list[ColumnElement[bool]], axis: str) -> list[Count]:
    if axis in ("region", "signal"):
        key: Any = Source.region if axis == "region" else ItemCard.signal_type
        statement = joined(select(key, func.count(distinct(Item.id)))).where(key.is_not(None))
    else:
        element = (
            func.jsonb_array_elements_text(ItemCard.themes).table_valued("value").lateral(axis)
        )
        key = element.c.value
        statement = joined(select(key, func.count(distinct(Item.id)))).join(element, true())
    rows = session.execute(statement.where(*conditions).group_by(key)).tuples()
    return [
        Count(key=str(k), count=int(c))
        for k, c in sorted(rows, key=lambda pair: (-int(pair[1]), str(pair[0])))
    ]


def topic_detail(
    session: Session,
    filters: ReaderFilters,
    window: Window,
    *,
    kind: str,
    value: str,
    now: datetime | None = None,
) -> TopicDetail:
    condition = topic_condition(kind, value)
    base = [*filters.conditions(), condition]
    windows = trailing_windows(window, TREND_WINDOWS)
    cutoffs = paced_cutoffs(windows, now) if now is not None else None
    series = _series(session, base, windows, kind, only=value, cutoffs=cutoffs).get(value)
    counts = series.counts if series else [0] * TREND_WINDOWS
    empty = dict.fromkeys((t.value for t in Track), 0)
    mix = _source_mix(session, base, window, kind).get(value)
    totals = _track_totals(session, filters.conditions(), window)
    topic = (
        _topic(value, series, mix, totals)
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
            baseline_tracks=empty,
            impacts=dict.fromkeys(IMPACTS, 0),
            regions=dict.fromkeys((r.value for r in Region), 0),
            first_seen={},
            official=0,
            effective_sources=None,
        )
    )
    if kind == "keyword":
        topic = _with_history(session, filters.conditions(), windows, [topic])[0]
    current = [*base, *_span([window])]
    related = _series(session, base, [window], "keyword")
    related.pop(value, None)
    keywords = sorted(related.items(), key=lambda kv: (-kv[1].counts[-1], kv[0]))[:12]
    named = _series(session, base, [window], "company")
    named.pop(value, None)
    companies = sorted(named.items(), key=lambda kv: (-kv[1].counts[-1], kv[0]))[:10]
    stories = feed(session, filters, window, sort="coverage", page=1, size=5, extra=[condition])
    registry = info_for(session) if kind in ("theme", "company") else {}
    info = registry.get(value) if kind == "company" else None
    return TopicDetail(
        kind=kind,
        topic=topic.model_copy(update={"label": info.name_ko or info.name}) if info else topic,
        themes=[c for c in _counts(session, current, "theme") if c.key != value][:8],
        keywords=[
            KeywordCount(key=key, label=s.label or key, count=s.counts[-1]) for key, s in keywords
        ],
        signal_types=_counts(session, current, "signal"),
        regions=_counts(session, current, "region"),
        stories=stories.items,
        companies=[
            KeywordCount(key=key, label=s.label or key, count=s.counts[-1]) for key, s in companies
        ],
        major_companies=[
            CompanyRef(key=c.key, label=c.name_ko or c.name, relation=c.relation, kind=c.kind)
            for c in sorted(registry.values(), key=lambda c: c.key)
            if kind == "theme" and value in c.themes
        ],
        profile=CompanyProfile(
            key=info.key,
            name=info.name,
            name_ko=info.name_ko,
            kind=info.kind,
            region=info.region,
            relation=info.relation,
            themes=info.themes,
        )
        if info
        else None,
    )
