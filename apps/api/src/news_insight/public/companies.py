"""Company radar (plan 12 §3): who is moving, in what way, where, and who is new.

Companies are a fourth radar dimension (`company_keys`), so momentum, lifecycle, track, impact and
region breakdowns come from the same engine and statistics as fields, themes and keywords. On top
of that this module reads what only makes sense for companies:

- self-announced vs reported by others (the company's own domains): a busy newsroom is not news,
  so the ranking is by reports from other outlets
- activity mix: the signal type whose share moved most against the earlier windows
- theme share of voice and leader changes, and companies entering a theme for the first time
- entrants: registered companies first reported recently and names the registry does not know
- co-mentions: company pairs named together more than chance, new pairs first
"""

from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from statistics import fmean

from sqlalchemy import ColumnElement, distinct, func, select, true
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.catalog import ORGANIZATIONS, CompanyKind
from news_insight.companies.service import CompanyInfo, candidates, info_for
from news_insight.content.models import Item
from news_insight.public.aggregates import KEYWORD_MIN_COUNT
from news_insight.public.filters import ReaderFilters, joined
from news_insight.public.keywords import company_element
from news_insight.public.periods import Window, trailing_windows
from news_insight.public.radar import (
    DEBUT_WINDOWS,
    TREND_WINDOWS,
    _bucket,
    _series,
    _source_mix,
    _span,
    _topic,
    _track_totals,
    paced_cutoffs,
    window_out,
)
from news_insight.public.schemas import (
    ActivityShift,
    CompanyPair,
    CompanyRadar,
    CompanyTopic,
    Count,
    Entrant,
    LeaderShare,
    RadarSignal,
    SignalFocus,
    ThemeEntry,
    ThemeLeaders,
)
from news_insight.public.signals import BASELINE_MIN, STATE_LABEL
from news_insight.public.stats import CARD_MIN, SIGNIFICANT_Z, two_proportion_z
from news_insight.sources.models import Source
from news_insight.taxonomy.catalog import LABELS

COMPANY_TOP = 40
ORGANIZATION_TOP = 12
THEME_LEADER_MIN = 10  # company-tagged reports in a theme before its leaders mean anything
LEADERS = 5
ENTRY_MIN = 3
ENTRY_SOURCES = 2
ENTRY_TOP = 12
ENTRANT_TOP = 12
PAIR_POOL = 60
PAIR_TOP = 24
PAIR_LIFT = 2.0
SHIFT_MIN_SHARE = 0.2  # a shift must also move the share by this much, not only be significant
SELF_MAX = 0.5  # surge cards need most reports from other outlets
COMPANY_TONES = ("company_surge", "company_shift", "theme_entry", "new_entrant")


def signal_label(key: str | None) -> str:
    return "-" if key is None else LABELS.get(key, key)


def is_self(domain: str | None, info: CompanyInfo | None) -> bool:
    if not domain or info is None:
        return False
    domain = domain.lower().removeprefix("www.")
    return any(domain == d or domain.endswith(f".{d}") for d in info.domains)


def _activity(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    registry: dict[str, CompanyInfo],
) -> tuple[dict[str, int], dict[str, Counter[str]], dict[str, Counter[str]]]:
    """(self-announced reports now, signal mix now, signal mix before) per company."""
    element = company_element("activity")
    key = element.c.value
    current = windows[-1]
    assert current.start is not None
    now_flag = Item.first_seen_at >= current.start
    rows = session.execute(
        joined(
            select(
                key,
                Source.official_domain,
                ItemCard.signal_type,
                now_flag,
                func.count(distinct(Item.id)),
            )
        )
        .join(element, true())
        .where(*conditions, *_span(windows))
        .group_by(key, Source.official_domain, ItemCard.signal_type, now_flag)
    ).tuples()
    own: dict[str, int] = defaultdict(int)
    mix_now: dict[str, Counter[str]] = defaultdict(Counter)
    mix_before: dict[str, Counter[str]] = defaultdict(Counter)
    for company, domain, signal_type, is_now, count in rows:
        company = str(company)
        if is_now:
            if is_self(domain, registry.get(company)):
                own[company] += int(count)
            if signal_type:
                mix_now[company][str(signal_type)] += int(count)
        elif signal_type:
            mix_before[company][str(signal_type)] += int(count)
    return dict(own), dict(mix_now), dict(mix_before)


def activity_shift(now: Counter[str], before: Counter[str]) -> ActivityShift | None:
    """Signal type with the largest significant share rise (current vs earlier windows)."""
    n_now, n_before = sum(now.values()), sum(before.values())
    if n_now < CARD_MIN or n_before < CARD_MIN:
        return None
    best: ActivityShift | None = None
    for signal_type, count in now.items():
        share, baseline = count / n_now, before.get(signal_type, 0) / n_before
        z = two_proportion_z(count, n_now, before.get(signal_type, 0), n_before)
        if (
            z >= SIGNIFICANT_Z
            and share - baseline >= SHIFT_MIN_SHARE
            and (best is None or z > best.z)
        ):
            best = ActivityShift(
                signal_type=signal_type,
                share=round(share, 3),
                baseline_share=round(baseline, 3),
                z=round(z, 2),
            )
    return best


Buckets = dict[tuple[str, str, int], tuple[int, int]]


def _themes(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    registry: dict[str, CompanyInfo],
) -> tuple[Buckets, dict[tuple[str, str, int], int], dict[tuple[str, int], int]]:
    """Company × theme per bucket (2 = current window, 1 = previous, 0 = earlier):
    (reports, sources), reports from other outlets than the company's own, and the theme's
    company-tagged reports in the last two windows."""
    last = len(windows) - 1
    bucket = _bucket(windows)
    company = company_element("company")
    theme = func.jsonb_array_elements_text(ItemCard.themes).table_valued("value").lateral("theme")
    rows = session.execute(
        joined(
            select(
                company.c.value,
                theme.c.value,
                bucket,
                Source.official_domain,
                func.count(distinct(Item.id)),
                func.count(distinct(Item.source_id)),
            )
        )
        .join(company, true())
        .join(theme, true())
        .where(*conditions, *_span(windows))
        .group_by(company.c.value, theme.c.value, bucket, Source.official_domain)
    ).tuples()
    pairs: Buckets = {}
    voice: dict[tuple[str, str, int], int] = defaultdict(int)
    for key, theme_key, index, domain, count, sources in rows:
        b = 2 if index == last else 1 if index == last - 1 else 0
        cell = (str(key), str(theme_key), b)
        reports, outlets = pairs.get(cell, (0, 0))
        # one row per domain: outlets add up (a domain is one outlet, give or take)
        pairs[cell] = (reports + int(count), outlets + int(sources))
        if not is_self(domain, registry.get(str(key))):
            voice[cell] += int(count)
    theme_only = func.jsonb_array_elements_text(ItemCard.themes).table_valued("value").lateral("t")
    totals: dict[tuple[str, int], int] = defaultdict(int)
    for theme_key, index, count in session.execute(
        joined(select(theme_only.c.value, bucket, func.count(distinct(Item.id))))
        .join(theme_only, true())
        .where(
            *conditions,
            *_span(windows[-2:]),
            func.jsonb_array_length(ItemCard.company_keys) > 0,
        )
        .group_by(theme_only.c.value, bucket)
    ).tuples():
        totals[(str(theme_key), 2 if index == last else 1)] += int(count)
    return pairs, dict(voice), dict(totals)


def theme_leaders(
    voice: dict[tuple[str, str, int], int],
    totals: dict[tuple[str, int], int],
    labels: dict[str, str],
    *,
    exclude: frozenset[str] = frozenset(),
) -> list[ThemeLeaders]:
    """Share of each theme's company-tagged reports that name a company, counting only reports
    from other outlets (a newsroom source would otherwise lead its own themes). Companies in
    `exclude` (organisations) are left out."""
    by_theme: dict[str, dict[int, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    for (company, theme, b), count in voice.items():
        if b and company not in exclude:
            by_theme[theme][b][company] = count
    result = []
    for theme, buckets in by_theme.items():
        total, previous_total = totals.get((theme, 2), 0), totals.get((theme, 1), 0)
        if total < THEME_LEADER_MIN:
            continue
        now = sorted(buckets.get(2, {}).items(), key=lambda kv: (-kv[1], kv[0]))
        before = sorted(buckets.get(1, {}).items(), key=lambda kv: (-kv[1], kv[0]))
        previous_leader = before[0][0] if before and previous_total >= THEME_LEADER_MIN else None
        leaders = [
            LeaderShare(
                key=key,
                label=labels.get(key, key),
                count=count,
                share=round(count / total * 100, 1),
                previous_share=(
                    round(buckets.get(1, {}).get(key, 0) / previous_total * 100, 1)
                    if previous_total
                    else None
                ),
            )
            for key, count in now[:LEADERS]
        ]
        result.append(
            ThemeLeaders(
                theme=theme,
                total=total,
                previous_total=previous_total,
                leaders=leaders,
                previous_leader=previous_leader,
                leader_changed=bool(
                    leaders and previous_leader and leaders[0].key != previous_leader
                ),
            )
        )
    result.sort(key=lambda t: (-t.total, t.theme))
    return result


def theme_entries(
    pairs: Buckets,
    registry: dict[str, CompanyInfo],
    labels: dict[str, str],
) -> list[ThemeEntry]:
    """Company × theme with enough reports now, none earlier in the span, outside its main
    themes: a launch, a partnership or a pivot into a new area."""
    seen_before = {(c, t) for (c, t, b), (count, _) in pairs.items() if b < 2 and count}
    entries = []
    for (company, theme, b), (count, sources) in pairs.items():
        info = registry.get(company)
        if (
            b != 2
            or info is None
            or CompanyKind(info.kind) in ORGANIZATIONS
            or theme in info.themes
            or (company, theme) in seen_before
            or count < ENTRY_MIN
            or sources < ENTRY_SOURCES
        ):
            continue
        entries.append(
            ThemeEntry(
                key=company,
                label=labels.get(company, company),
                theme=theme,
                count=count,
                sources=sources,
            )
        )
    entries.sort(key=lambda e: (-e.count, -e.sources, e.key, e.theme))
    return entries[:ENTRY_TOP]


def _first_ever(
    session: Session, conditions: list[ColumnElement[bool]], keys: list[str]
) -> dict[str, datetime]:
    if not keys:
        return {}
    element = company_element("first")
    rows = session.execute(
        joined(select(element.c.value, func.min(Item.first_seen_at)))
        .join(element, true())
        .where(*conditions, element.c.value.in_(keys))
        .group_by(element.c.value)
    ).tuples()
    return {str(k): at for k, at in rows}


def entrants(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    topics: list[CompanyTopic],
    now: datetime,
) -> list[Entrant]:
    current = windows[-1]
    recent = windows[-DEBUT_WINDOWS:][0].start
    assert current.start is not None and recent is not None
    active = [t for t in topics if t.counts[-1] >= KEYWORD_MIN_COUNT]
    first = _first_ever(session, conditions, [t.key for t in active])
    found = [
        Entrant(
            key=t.key,
            name=t.label or t.name,
            registered=True,
            cards=t.counts[-1],
            sources=t.sources,
            first_seen=first[t.key],
        )
        for t in active
        if t.key in first and first[t.key] >= recent
    ]
    until = min(now, current.end)
    days = max(1, round((until - current.start).total_seconds() / 86400))
    for row in candidates(
        session, now=until, days=days, min_count=ENTRY_MIN, min_sources=ENTRY_SOURCES
    ):
        if row.earlier == 0:
            found.append(
                Entrant(
                    key=row.key,
                    name=row.name,
                    registered=False,
                    cards=row.cards,
                    sources=row.sources,
                )
            )
    found.sort(key=lambda e: (-e.sources, -e.cards, e.key))
    return found[:ENTRANT_TOP]


def company_pairs(
    session: Session,
    conditions: list[ColumnElement[bool]],
    windows: list[Window],
    topics: list[CompanyTopic],
    total: int,
) -> list[CompanyPair]:
    """Companies named together this window; lift > 1 means more than chance."""
    pool = {t.key: t.counts[-1] for t in topics if t.counts[-1] >= KEYWORD_MIN_COUNT}
    pool = dict(sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))[:PAIR_POOL])
    if len(pool) < 2 or not total:
        return []
    last = len(windows) - 1
    rows = session.execute(
        joined(select(Item.id, _bucket(windows), ItemCard.company_keys, ItemCard.signal_type))
        .where(*conditions, *_span(windows), func.jsonb_array_length(ItemCard.company_keys) >= 2)
        .distinct()
    ).tuples()
    now: Counter[tuple[str, str]] = Counter()
    before: Counter[tuple[str, str]] = Counter()
    kinds: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for _, index, keys, signal_type in rows:
        named = sorted({k for k in keys or [] if k in pool})
        for pair in combinations(named, 2):
            if index == last:
                now[pair] += 1
                if signal_type:
                    kinds[pair][str(signal_type)] += 1
            else:
                before[pair] += 1
    pairs = [
        CompanyPair(
            a=a,
            b=b,
            count=count,
            lift=round(count * total / (pool[a] * pool[b]), 2),
            is_new=before[(a, b)] == 0,
            signal_type=kinds[(a, b)].most_common(1)[0][0] if kinds[(a, b)] else None,
        )
        for (a, b), count in now.items()
        if count >= KEYWORD_MIN_COUNT
    ]
    pairs.sort(key=lambda p: (-p.count, -p.lift, p.a, p.b))
    return pairs[:PAIR_TOP]


def _tagged(
    session: Session, conditions: list[ColumnElement[bool]], windows: list[Window]
) -> list[int]:
    bucket = _bucket(windows).label("bucket")
    rows = dict(
        session.execute(
            joined(select(bucket, func.count(distinct(Item.id))))
            .where(
                *conditions,
                *_span(windows),
                func.jsonb_array_length(ItemCard.company_keys) > 0,
            )
            .group_by(bucket)
        )
        .tuples()
        .all()
    )
    return [int(rows.get(i, 0)) for i in range(len(windows))]


def company_radar(
    session: Session, filters: ReaderFilters, window: Window, current_key: str, now: datetime
) -> CompanyRadar:
    base = filters.conditions()
    windows = trailing_windows(window, TREND_WINDOWS)
    cutoffs = paced_cutoffs(windows, now)
    registry = info_for(session)
    series = _series(session, base, windows, "company", cutoffs=cutoffs)
    mixes = _source_mix(session, base, window, "company")
    totals = _track_totals(session, base, window)
    own, mix_now, mix_before = _activity(session, base, windows, registry)
    pairs_by_theme, voice, theme_totals = _themes(session, base, windows, registry)
    top_themes: dict[str, list[Count]] = defaultdict(list)
    for (company, theme, b), (count, _) in sorted(pairs_by_theme.items(), key=lambda kv: -kv[1][0]):
        if b == 2 and len(top_themes[company]) < 3:
            top_themes[company].append(Count(key=theme, count=count))
    topics: list[CompanyTopic] = []
    for key, s in series.items():
        info = registry.get(key)
        if info is None:
            continue
        base_topic = _topic(key, s, mixes.get(key), totals)
        topics.append(
            CompanyTopic(
                **base_topic.model_dump(),
                name=info.name,
                name_ko=info.name_ko,
                kind=info.kind,
                region=info.region,
                relation=info.relation,
                self_reports=own.get(key, 0),
                signal_mix=dict(mix_now.get(key, Counter())),
                baseline_mix=dict(mix_before.get(key, Counter())),
                shift=activity_shift(mix_now.get(key, Counter()), mix_before.get(key, Counter())),
                top_themes=top_themes.get(key, []),
            )
        )
    # ranked by reports from other outlets: a busy newsroom is not news
    topics.sort(key=lambda t: (-(t.counts[-1] - t.self_reports), -t.z, t.key))
    # a company quiet this window is not news unless it is falling
    shown = [t for t in topics if t.counts[-1] > 0 or t.state == "falling"]
    companies = [t for t in shown if CompanyKind(t.kind) not in ORGANIZATIONS]
    organizations = [t for t in shown if CompanyKind(t.kind) in ORGANIZATIONS]
    labels = {t.key: t.label or t.name for t in topics}
    tagged = _tagged(session, base, windows)
    # "first", "new" and "entered" need earlier windows with reports (the radar's own gate)
    history = has_history(tagged)
    pairs = company_pairs(session, base, windows, topics, tagged[-1])
    body = CompanyRadar(
        window=window_out(window, current_key, now),
        periods=[w.key for w in windows],
        tagged=tagged,
        companies=companies[:COMPANY_TOP],
        organizations=organizations[:ORGANIZATION_TOP],
        theme_leaders=theme_leaders(
            voice,
            theme_totals,
            labels,
            exclude=frozenset(t.key for t in organizations),
        ),
        entries=theme_entries(pairs_by_theme, registry, labels) if history else [],
        entrants=entrants(session, base, windows, companies, now) if history else [],
        pairs=pairs if history else [p.model_copy(update={"is_new": False}) for p in pairs],
    )
    body.signals = company_signals(body) if history else []
    return body


def has_history(tagged: list[int]) -> bool:
    earlier = tagged[:-1]
    return bool(earlier) and sum(1 for c in earlier if c > 0) >= BASELINE_MIN * len(earlier)


def _scored(topic: CompanyTopic) -> list[int]:
    return topic.paced or topic.counts


def company_signals(radar: CompanyRadar) -> list[RadarSignal]:
    """One card per tone at most, each company on one card at most (same rules as the radar)."""
    signals: list[RadarSignal] = []
    used: set[str] = set()

    def push(tone: str, title: str, detail: str, kind: str, key: str, score: float) -> None:
        signals.append(
            RadarSignal(
                tone=tone,
                title=title,
                detail=detail,
                focus=SignalFocus(kind=kind, key=key),
                score=round(score, 2),
            )
        )
        used.add(key)

    surging = [
        t
        for t in radar.companies
        if t.state == "surging"
        and t.counts[-1] - t.self_reports >= CARD_MIN
        and t.self_reports <= SELF_MAX * t.counts[-1]
    ]
    if surging:
        top = max(surging, key=lambda t: t.z)
        counts = _scored(top)
        main = max(top.signal_mix.items(), key=lambda kv: kv[1])[0] if top.signal_mix else None
        push(
            "company_surge",
            top.label or top.name,
            f"{counts[-1]}건, 직전 평균 {fmean(counts[:-1]):.1f}건 대비 z {top.z:+.1f}"
            f" · 출처 {top.sources}곳 · 주 유형 {signal_label(main)}"
            f" · {STATE_LABEL.get(top.state or '', '')}",
            "company",
            top.key,
            top.z,
        )
    shifted = [t for t in radar.companies if t.shift is not None and t.key not in used]
    if shifted:
        top = max(shifted, key=lambda t: t.shift.z if t.shift else 0.0)
        assert top.shift is not None
        push(
            "company_shift",
            top.label or top.name,
            f"{signal_label(top.shift.signal_type)} 비중 {top.shift.baseline_share * 100:.0f}%"
            f" → {top.shift.share * 100:.0f}% (z {top.shift.z:+.1f})",
            "company",
            top.key,
            top.shift.z,
        )
    entry = next((e for e in radar.entries if e.key not in used), None)
    if entry:
        push(
            "theme_entry",
            f"{entry.label} → {LABELS.get(entry.theme, entry.theme)}",
            f"주력 테마 밖 첫 보도 {entry.count}건 · 출처 {entry.sources}곳",
            "company",
            entry.key,
            float(entry.count),
        )
    entrant = next((e for e in radar.entrants if e.key not in used), None)
    if entrant:
        push(
            "new_entrant",
            entrant.name,
            f"{entrant.cards}건 · 출처 {entrant.sources}곳"
            + (" · 레지스트리 미등록" if not entrant.registered else " · 최근 첫 보도"),
            "company" if entrant.registered else "search",
            entrant.key if entrant.registered else entrant.name,
            float(entrant.sources),
        )
    return signals
