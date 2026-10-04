"""Rule-based reading of the radar: the few things a strategy reader should look at first.

Each rule yields at most one card and each theme appears on one card at most. Every rule decides
with the shared tests in `public.stats` (checklist STAT-3) and ranks with them, so small samples
are handled the same way everywhere; the cards are stored daily and given to the digest and the
strategy prompts as evidence (PRD-1). Track comparisons use the mean of the baseline windows (the
same elapsed share while a window is in progress), not the single previous window.
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from math import floor
from statistics import fmean
from typing import TypeVar

from news_insight.public.schemas import Radar, RadarSignal, SignalFocus, Topic
from news_insight.public.stats import (
    CARD_MIN,
    SIGNIFICANT_Z,
    rate_z,
    shrunk_share,
    two_proportion_z,
    zero_chance,
)
from news_insight.taxonomy.catalog import LABELS

TONES = (
    "surge",
    "event",
    "new",
    "back",
    "early",
    "pull",
    "shift",
    "hype",
    "thin",
    "gap",
    "link",
    "cool",
)
BASELINE_UNIT = {"day": "일", "week": "주", "month": "개월", "quarter": "분기"}
STATE_LABEL = {
    "new": "신규",
    "surging": "급상승",
    "rising": "상승",
    "steady": "유지",
    "falling": "하락",
}
MOVE = 1.5  # effect size: a move must also be this large, not only significant
SHARE_DROP = 0.2  # research share must fall by at least this much for "shift"
GAP_CHANCE = 0.05  # no Korean source although the usual rate makes that this unlikely
NARROW_SOURCES = 2.5  # effective number of outlets below which a rise is thin
LINK_LIFT = 2.0
FIELD_LINK_MIN = 3

T = TypeVar("T")
Candidates = dict[str, list[str]]


def _last(values: Sequence[int]) -> int:
    return values[-1] if values else 0


def _mean(values: Sequence[float]) -> float:
    return fmean(values) if values else 0.0


def _chatter(mix: dict[str, int]) -> int:
    return mix.get("news", 0) + mix.get("community", 0)


def _research(mix: dict[str, int]) -> int:
    return mix.get("research_ip", 0) + mix.get("oss", 0)


def _pct(share: float) -> str:
    return f"{round(share * 100)}%"


def _z(z: float) -> str:
    sign = "+" if z > 0 else ("−" if z < 0 else "±")
    return f"{sign}{abs(z):.1f}σ"


def scored(topic: Topic) -> list[int]:
    """The counts change, z and state were scored on."""
    return topic.paced or topic.counts


def label(kind: str, topic: Topic) -> str:
    if kind in ("field", "theme"):
        return LABELS.get(topic.key, topic.key)
    return topic.label or topic.key


def korea_gaps(radar: Radar) -> list[Topic]:
    """Keywords with no Korean source where the usual Korean share makes that unlikely."""
    reports = sum(sum(f.regions.values()) for f in radar.fields)
    korean = sum(f.regions.get("kr", 0) for f in radar.fields)
    rate = korean / reports if reports else 0.0
    rows = [
        k
        for k in radar.keywords
        if k.state != "falling"
        and k.regions.get("kr", 0) == 0
        and zero_chance(_last(k.counts), rate) <= GAP_CHANCE
    ]
    return sorted(rows, key=lambda k: (-_last(k.counts), -k.z, k.key))


def share_drop_z(topic: Topic) -> float:
    """z of the fall in research share from the baseline windows to this one."""
    base, now = topic.baseline_tracks, topic.tracks
    return two_proportion_z(_research(base), sum(base.values()), _research(now), sum(now.values()))


def _share_drop(topic: Topic) -> float:
    base, now = sum(topic.baseline_tracks.values()), sum(topic.tracks.values())
    if not base or not now:
        return 0.0
    return _research(topic.baseline_tracks) / base - _research(topic.tracks) / now


def _days_since(iso: datetime | None, until: datetime) -> int:
    if iso is None:
        return 0
    return max(0, floor((until - iso).total_seconds() / 86400))


def radar_signals(
    radar: Radar, *, now: datetime | None = None, candidates: Candidates | None = None
) -> list[RadarSignal]:
    """The radar's cards. With `candidates`, every rule's matches before ranking are collected
    (the QA regression checks planted patterns against them)."""
    window = radar.window
    until = min(window.end, now or window.end).astimezone(UTC)
    history = len(radar.periods) - 1
    span = f"직전 {history}{BASELINE_UNIT.get(window.kind, '기간')}"
    baseline = f"{span} 같은 시점" if window.is_current else span
    themes = [t for t in radar.themes if _last(scored(t)) > 0 or _mean(scored(t)[:-1]) > 0]
    signals: list[RadarSignal] = []
    used: set[str] = set()

    def per_window(mix: dict[str, int], pick: Callable[[dict[str, int]], int]) -> float:
        return pick(mix) / max(history, 1)

    def pick(
        tone: str,
        rows: list[T],
        score: Callable[[T], float],
        key: Callable[[T], str],
        fresh: bool = False,
    ) -> T | None:
        if candidates is not None:
            candidates[tone] = [key(row) for row in rows]
        pool = [row for row in rows if not (fresh and key(row) in used)]
        return max(pool, key=score) if pool else None

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

    def topic_key(t: Topic) -> str:
        return t.key

    # ── surge: the lifecycle state already tests the rise (count z, effect size, sources)
    surge = pick("surge", [t for t in themes if t.state == "surging"], lambda t: t.z, topic_key)
    if surge:
        counts = scored(surge)
        push(
            "surge",
            label("theme", surge),
            f"{_last(counts)}건, {baseline} 평균 {_mean(counts[:-1]):.1f}건 대비 {_z(surge.z)}"
            f" · 출처 {surge.sources}곳",
            "theme",
            surge.key,
            surge.z,
        )

    # ── event: the busiest anomaly day inside the window (a launch, an announcement, an incident)
    window_start = window.start.astimezone(UTC).date() if window.start else None
    anomalies = [
        a for a in radar.calendar.anomalies if window_start is None or a.day >= window_start
    ]
    event = pick(
        "event",
        anomalies,
        lambda a: a.z,
        lambda a: a.keywords[0].key if a.keywords else a.field,
    )
    if event:
        words = ", ".join(k.label for k in event.keywords)
        ratio = event.count / max(event.expected, 1)
        push(
            "event",
            f"{event.day.month}/{event.day.day} {LABELS.get(event.field, event.field)}",
            f"하루 {event.count}건, 평소 같은 요일 {event.expected:.1f}건의 {ratio:.1f}배"
            + (f" · {words}" if words else ""),
            "keyword" if event.keywords else "field",
            event.keywords[0].key if event.keywords else event.field,
            event.z,
        )

    # ── new: first reports ever (or a debut still growing), largest first
    fresh = sorted(
        (
            k
            for k in radar.keywords
            if not k.returning and (k.state == "new" or (k.debut and k.state != "falling"))
        ),
        key=lambda k: (-_last(k.counts), -k.z, k.key),
    )
    if candidates is not None:
        candidates["new"] = [k.key for k in fresh]
    if fresh:
        lead = fresh[0]
        others = ", ".join(label("keyword", k) for k in fresh[1:4])
        push(
            "new",
            label("keyword", lead),
            f"처음 보도된 지 {_days_since(lead.first_ever, until)}일, "
            f"이번 기간 {_last(lead.counts)}건"
            f" · 출처 {lead.sources}곳" + (f" · 함께 등장: {others}" if others else ""),
            "keyword",
            lead.key,
            float(_last(lead.counts)),
        )

    # ── back: silent through the baseline, reported again
    back = pick(
        "back",
        [k for k in radar.keywords if k.returning],
        lambda k: _last(k.counts),
        topic_key,
    )
    if back:
        push(
            "back",
            label("keyword", back),
            f"{span} 동안 없다가 {_last(back.counts)}건 · 첫 보도는 "
            f"{_days_since(back.first_ever, until)}일 전: 다시 주목받는 이유 확인",
            "keyword",
            back.key,
            float(_last(back.counts)),
        )

    # ── early: rising and mostly papers and code; ranked with the share shrunk toward the
    # overall one, so a small theme does not win on a lucky ratio
    items, research_items = sum(radar.kpis.items[-1:]), sum(radar.kpis.research[-1:])
    research_prior = research_items / items if items else 0.0

    def research_share(t: Topic) -> float:
        return shrunk_share(_research(t.tracks), sum(t.tracks.values()), research_prior)

    def research_led(t: Topic) -> bool:
        total = sum(t.tracks.values())
        return total >= CARD_MIN and t.z >= 1 and _research(t.tracks) / total >= 0.5

    early = pick(
        "early",
        [t for t in themes if research_led(t)],
        lambda t: t.z * research_share(t),
        topic_key,
        fresh=True,
    )
    if early:
        share = _research(early.tracks) / max(sum(early.tracks.values()), 1)
        push(
            "early",
            label("theme", early),
            f"논문·오픈소스 비중 {_pct(share)}, {_z(early.z)}: "
            "시장 보도보다 연구·구현이 앞서는 초기 단계",
            "theme",
            early.key,
            early.z * research_share(early),
        )

    # ── pull: more items gaining reactions (stars, points) than the theme's share of mentions
    # predicts, and a reaction share at least MOVE times the mention share
    by_key = {t.key: t for t in themes}
    mentions = sum(_last(t.counts) for t in themes)
    reactions = sum(e.score for e in radar.engagement.themes)
    measured = radar.engagement.measured

    def pull_z(key: str, reacting: int) -> float:
        topic = by_key[key]
        return rate_z(reacting, measured * _last(topic.counts) / mentions)

    pulled = [
        e
        for e in radar.engagement.themes
        if e.key in by_key
        and mentions > 0
        and reactions > 0
        and e.score / reactions >= MOVE * _last(by_key[e.key].counts) / mentions
        and pull_z(e.key, e.items) >= SIGNIFICANT_Z
    ]
    pull = pick("pull", pulled, lambda e: pull_z(e.key, e.items), lambda e: e.key, fresh=True)
    if pull:
        topic = by_key[pull.key]
        push(
            "pull",
            label("theme", topic),
            f"언급 비중 {_pct(_last(topic.counts) / mentions)}인데 반응(스타·포인트 증가) 비중 "
            f"{_pct(pull.score / reactions)} · {pull.items}건: 개발자 채택이 보도보다 앞섬",
            "theme",
            topic.key,
            pull_z(pull.key, pull.items),
        )

    # ── shift: the research share fell, tested as two proportions
    shift = pick(
        "shift",
        [t for t in themes if _share_drop(t) >= SHARE_DROP and share_drop_z(t) >= SIGNIFICANT_Z],
        share_drop_z,
        topic_key,
        fresh=True,
    )
    if shift:
        before = _research(shift.baseline_tracks) / max(sum(shift.baseline_tracks.values()), 1)
        after = _research(shift.tracks) / max(sum(shift.tracks.values()), 1)
        push(
            "shift",
            label("theme", shift),
            f"논문·오픈소스 비중 {baseline} {_pct(before)} → 이번 {_pct(after)}: "
            "연구에서 제품·시장 이야기로 넘어가는 중",
            "theme",
            shift.key,
            share_drop_z(shift),
        )

    # ── hype: news and community well above their usual rate while research is not
    def hype_z(t: Topic) -> float:
        return rate_z(_chatter(t.tracks), per_window(t.baseline_tracks, _chatter))

    def hyped(t: Topic) -> bool:
        usual = per_window(t.baseline_tracks, _chatter)
        usual_research = per_window(t.baseline_tracks, _research)
        return (
            _chatter(t.tracks) >= CARD_MIN
            and usual > 0
            and _chatter(t.tracks) >= usual * MOVE
            and hype_z(t) >= SIGNIFICANT_Z
            and rate_z(_research(t.tracks), usual_research) < 1
        )

    hype = pick("hype", [t for t in themes if hyped(t)], hype_z, topic_key, fresh=True)
    if hype:
        usual = per_window(hype.baseline_tracks, _chatter)
        usual_research = per_window(hype.baseline_tracks, _research)
        push(
            "hype",
            label("theme", hype),
            f"뉴스·커뮤니티 {_chatter(hype.tracks)}건으로 평소({usual:.1f}건)의 "
            f"{_chatter(hype.tracks) / usual:.1f}배, 논문·오픈소스는 {_research(hype.tracks)}건"
            f"(평소 {usual_research:.1f}건): 화제가 실체보다 앞섬",
            "theme",
            hype.key,
            hype_z(hype),
        )

    # ── thin: a rise carried by one or two outlets, or mostly by vendors' own newsrooms
    def thin_rise(t: Topic) -> bool:
        narrow = t.effective_sources is not None and t.effective_sources < NARROW_SOURCES
        news = t.tracks.get("news", 0)
        vendor = news >= CARD_MIN - 1 and t.official / news >= 0.5
        return _last(scored(t)) >= CARD_MIN and t.z >= 1 and (narrow or vendor)

    thin = pick("thin", [t for t in themes if thin_rise(t)], lambda t: t.z, topic_key, fresh=True)
    if thin:
        parts = []
        if thin.effective_sources is not None:
            parts.append(f"실효 출처 {thin.effective_sources:.1f}곳")
        if thin.official and thin.tracks.get("news"):
            parts.append(f"뉴스 중 공식 발표 {_pct(thin.official / thin.tracks['news'])}")
        push(
            "thin",
            label("theme", thin),
            f"{_last(scored(thin))}건, {_z(thin.z)} 상승이지만 {' · '.join(parts)}: "
            "독립 보도로 확인 필요",
            "theme",
            thin.key,
            thin.z,
        )

    # ── gap: reported abroad, no Korean source although one would usually be there
    gaps = korea_gaps(radar)
    if candidates is not None:
        candidates["gap"] = [k.key for k in gaps]
    if gaps:
        lead = gaps[0]
        others = ", ".join(label("keyword", k) for k in gaps[1:3])
        state = f" · {STATE_LABEL[lead.state]}" if lead.state in STATE_LABEL else ""
        push(
            "gap",
            label("keyword", lead),
            f"해외 {_last(lead.counts)}건{state}, 국내 출처 0건"
            + (f" · 같은 상황: {others}" if others else ""),
            "keyword",
            lead.key,
            float(_last(lead.counts)),
        )

    # ── link: two technologies far more often together than chance, new or across categories
    keywords = {k.key: k for k in radar.keywords}

    def cross_field(a: str, b: str) -> bool:
        fa, fb = (
            keywords[a].field if a in keywords else None,
            (keywords[b].field if b in keywords else None),
        )
        return fa is not None and fb is not None and fa != fb

    link = pick(
        "link",
        [p for p in radar.pairs if p.lift >= LINK_LIFT and (p.is_new or cross_field(p.a, p.b))],
        lambda p: (
            (1000 if p.is_new else 0) + (500 if cross_field(p.a, p.b) else 0) + p.count * p.lift
        ),
        lambda p: f"{p.a}×{p.b}",
    )
    field_link = max(
        (lnk for lnk in radar.field_links if lnk.previous == 0 and lnk.count >= FIELD_LINK_MIN),
        key=lambda lnk: lnk.count,
        default=None,
    )
    if link:
        a, b = keywords.get(link.a), keywords.get(link.b)
        fields = [f for f in (a.field if a else None, b.field if b else None) if f in LABELS]
        across = f" · {'↔'.join(LABELS[f] for f in fields)}" if len(set(fields)) == 2 else ""
        push(
            "link",
            f"{label('keyword', a) if a else link.a} × {label('keyword', b) if b else link.b}",
            f"함께 언급 {link.count}건, 우연 대비 {link.lift:.1f}배"
            + (" · 이번 기간 첫 동시 언급" if link.is_new else "")
            + across,
            "keyword",
            link.a,
            link.lift,
        )
    elif field_link:
        push(
            "link",
            f"{LABELS.get(field_link.a, field_link.a)} × {LABELS.get(field_link.b, field_link.b)}",
            f"두 카테고리에 함께 분류된 보도 {field_link.count}건, 직전 기간 0건: 새로 생긴 교차점",
            "field",
            field_link.a,
            float(field_link.count),
        )

    # ── cool: the lifecycle state already tests the fall
    cool = pick(
        "cool",
        [t for t in themes if t.state == "falling"],
        lambda t: -t.z,
        topic_key,
        fresh=True,
    )
    if cool:
        counts = scored(cool)
        push(
            "cool",
            label("theme", cool),
            f"{_last(counts)}건, {baseline} 평균 {_mean(counts[:-1]):.1f}건 대비 {_z(cool.z)}",
            "theme",
            cool.key,
            -cool.z,
        )
    return signals
