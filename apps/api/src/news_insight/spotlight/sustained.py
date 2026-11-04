"""지속 주목: per section, what has held attention over several of the last seven days (B3).

The span is the seven days up to the window end (the freeze time). Events count the distinct
KST days on which members of their story were first collected; open-source repositories and
models the days a trending list showed them; papers the days news or the community pointed at
them; the leaderboards the models that held a top-5 place throughout. Whatever the published
spotlight listed on two or more of the previous six days joins as well. Each section keeps its
strongest 15 (cids `<prefix>s<n>`). Whether a candidate repeats a 최근 24시간 pick is decided
when the day is written, against what was picked."""

import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item, ItemDedup, ItemMetricSnapshot
from news_insight.public.benchmarks import top_holders
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.spotlight.candidates import (
    AI_FIELD,
    AI_SIGNALS,
    AI_TRACKS,
    CID_PREFIX,
    ELIGIBLE,
    GITHUB_DAILY,
    GITHUB_WEEKLY,
    HF_TRENDING,
    INTERVIEW_CATEGORIES,
    INTERVIEW_PATTERN,
    KST,
    MIN_NEWS_SOURCES,
    OSS_REF_KINDS,
    PATENT_OFFICE,
    RESEARCH_REF_KINDS,
    SECTIONS,
    Candidate,
    Fold,
    Row,
    Scorer,
    _cards,
    _fold_stories,
    _lead,
    _ref_groups,
    _select_rows,
    _stories,
    _summary,
    model_key,
    window,
)
from news_insight.spotlight.models import Spotlight, SpotlightEntry, SpotlightStatus
from news_insight.stories.models import ItemRef, StoryItem

logger = logging.getLogger(__name__)

SPAN_DAYS = 7
MIN_DAYS = 3  # distinct days of attention within the span
MIN_RESEARCH_DAYS = 2
MIN_RESEARCH_MENTIONS = 3
LISTED_LOOKBACK = 6  # previous days of published spotlights read
MIN_LISTED_DAYS = 2
BENCHMARK_TOP = 5
LIMIT = 15
OSS_RANK_BONUS = 30
TREND_SOURCES = (GITHUB_DAILY, GITHUB_WEEKLY, HF_TRENDING)
BASIS = {GITHUB_DAILY: "github_daily", GITHUB_WEEKLY: "github_weekly", HF_TRENDING: "hf_trending"}


def span(day: date) -> tuple[datetime, datetime]:
    """Seven KST dates up to the briefing day's window end: from midnight six days before the
    briefing date (its own date holds the window's last 4 h 40 min)."""
    end = window(day)[1]
    start = datetime.combine(day - timedelta(days=SPAN_DAYS - 1), time(0), tzinfo=KST)
    return start.astimezone(UTC), end


def _kst_day(at: datetime) -> date:
    return at.astimezone(KST).date()


def _kst_date(column: Any) -> Any:
    return cast(func.timezone("Asia/Seoul", column), Date)


@dataclass
class _StoryStats:
    fold: Fold
    rows: list[Row]  # the fold's rows that make it qualify for a section
    days: set[date]
    sources: int
    community: int


def _story_rows(session: Session, start: datetime, end: datetime) -> list[Row]:
    """Members, collected in the span, of the stories whose members were first collected on at
    least MIN_DAYS distinct KST days of it."""
    day = _kst_date(Item.first_seen_at)
    active = (
        select(StoryItem.story_id)
        .join(Item, Item.id == StoryItem.item_id)
        .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
        .where(
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
            Item.canary.is_(False),
            ELIGIBLE,
        )
        .group_by(StoryItem.story_id)
        .having(func.count(distinct(day)) >= MIN_DAYS)
    )
    return _select_rows(
        session,
        Item.first_seen_at >= start,
        Item.first_seen_at < end,
        StoryItem.story_id.in_(active),
        ELIGIBLE,
    )


def _card_marks(
    session: Session, item_ids: Sequence[int]
) -> dict[int, tuple[str | None, str | None]]:
    """(field, signal type) of each item's ready card."""
    if not item_ids:
        return {}
    return {
        item_id: (field, signal)
        for item_id, field, signal in session.execute(
            select(ItemCard.item_id, ItemCard.field, ItemCard.signal_type).where(
                ItemCard.item_id.in_(list(item_ids)), ItemCard.status == CardStatus.READY
            )
        )
    }


def _story_drafts(
    session: Session,
    section: str,
    folds: Sequence[Fold],
    matches: Callable[[Row], bool],
    *,
    days_of: Callable[[Fold], list[Row]] | None = None,
) -> list[Candidate]:
    """One draft per story that has rows the section takes and was active on MIN_DAYS days:
    score = sources of those rows × 100 + community posts of the story × 10 + days × 20. Only
    the section's own rows count as its sources and speak for it (the lead, the items), so a
    big story with a single launch or interview headline does not lead every section."""
    stats: list[_StoryStats] = []
    for fold in folds:
        rows = [row for row in fold.rows if matches(row)]
        if not rows:
            continue
        counted = days_of(fold) if days_of is not None else fold.rows
        days = {_kst_day(row.item.first_seen_at) for row in counted}
        if len(days) < MIN_DAYS:
            continue
        stats.append(
            _StoryStats(
                fold=fold,
                rows=rows,
                days=days,
                sources=len({row.item.source_id for row in rows}),
                community=sum(1 for row in fold.rows if row.item.track is Track.COMMUNITY),
            )
        )
    if section == "news":
        stats = [s for s in stats if s.sources >= MIN_NEWS_SOURCES]
    stories = _stories(session, [s.fold for s in stats])
    leads = [_lead(Fold(s.fold.story_id, s.rows), stories.get(s.fold.story_id or 0)) for s in stats]
    cards = _cards(session, [lead.item.id for lead in leads])
    drafts: list[Candidate] = []
    for found, lead in zip(stats, leads, strict=True):
        story = stories.get(found.fold.story_id or 0)
        card = cards.get(lead.item.id)
        # the story's own title speaks for its representative only
        story_title = (
            story.title_ko
            if story is not None and story.representative_item_id == lead.item.id
            else None
        )
        title = (card.title_ko if card is not None else None) or story_title or lead.item.title
        drafts.append(
            Candidate(
                cid="",
                section=section,
                key=f"story:{found.fold.story_id}",
                item_ids=[lead.item.id, *(r.item.id for r in found.rows if r is not lead)],
                title_ko=title,
                summary_ko=_summary(card),
                url=lead.item.url,
                metrics={
                    "source_count": found.sources,
                    "community_mentions": found.community,
                    "days_active": len(found.days),
                    "first_seen": min(found.days).isoformat(),
                },
                score=float(found.sources * 100 + found.community * 10 + len(found.days) * 20),
                stat_rank=0,
                group="sustained",
            )
        )
    return drafts


def _story_sections(session: Session, start: datetime, end: datetime) -> dict[str, list[Candidate]]:
    rows = _story_rows(session, start, end)
    folds = [fold for fold in _fold_stories(rows) if fold.story_id is not None]
    marks = _card_marks(session, [row.item.id for row in rows])

    def signal(row: Row) -> str | None:
        return marks.get(row.item.id, (None, None))[1]

    def is_ai(row: Row) -> bool:
        field, kind = marks.get(row.item.id, (None, None))
        return field == AI_FIELD and kind in AI_SIGNALS and row.item.track in AI_TRACKS

    def is_interview(row: Row) -> bool:
        return row.category in INTERVIEW_CATEGORIES or (
            row.item.track is Track.NEWS and bool(INTERVIEW_PATTERN.search(row.item.title))
        )

    def community_rows(fold: Fold) -> list[Row]:
        return [row for row in fold.rows if row.item.track is Track.COMMUNITY]

    return {
        "news": _story_drafts(session, "news", folds, lambda r: r.item.track is Track.NEWS),
        "product": _story_drafts(session, "product", folds, lambda r: signal(r) == "launch"),
        "ai": _story_drafts(session, "ai", folds, is_ai),
        "interview": _story_drafts(session, "interview", folds, is_interview),
        "patent": _story_drafts(
            session,
            "patent",
            folds,
            lambda r: signal(r) == "ip" or r.category == PATENT_OFFICE,
        ),
        "community": _story_drafts(
            session,
            "community",
            folds,
            lambda r: r.item.track is Track.COMMUNITY,
            days_of=community_rows,
        ),
    }


def _oss(session: Session, start: datetime, end: datetime, scorer: Scorer) -> list[Candidate]:
    """Repositories and models a trending list showed on MIN_DAYS days of the span (listings
    of one repository fold): days × 20 + (30 - best GitHub rank) + z."""
    shown: dict[int, set[date]] = defaultdict(set)
    best_rank: dict[int, int] = {}
    for item_id, captured_at, snapped in session.execute(
        select(
            ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at, ItemMetricSnapshot.metrics
        )
        .join(Item, Item.id == ItemMetricSnapshot.item_id)
        .join(Source, Source.id == Item.source_id)
        .where(
            ItemMetricSnapshot.captured_at >= start,
            ItemMetricSnapshot.captured_at < end,
            Item.canary.is_(False),
            Source.key.in_(TREND_SOURCES),
        )
    ):
        shown[item_id].add(_kst_day(captured_at))
        rank = snapped.get("rank") if isinstance(snapped, dict) else None
        if isinstance(rank, int) and not isinstance(rank, bool):
            best_rank[item_id] = min(rank, best_rank.get(item_id, rank))
    if not shown:
        return []
    rows = _select_rows(session, Item.id.in_(list(shown)), ELIGIBLE)
    scorer.add(rows)
    groups = _ref_groups(session, start, end, rows, OSS_REF_KINDS)
    cards = _cards(session, [row.item.id for row in rows])
    order = {key: n for n, key in enumerate(TREND_SOURCES)}
    drafts: list[Candidate] = []
    for group in groups:
        days = set().union(*(shown[row.item.id] for row in group.rows))
        if len(days) < MIN_DAYS:
            continue
        lead = min(group.rows, key=lambda r: (order[r.source_key], best_rank.get(r.item.id, 999)))
        ranks = [best_rank[r.item.id] for r in group.rows if r.item.id in best_rank]
        top = min(ranks) if ranks else None
        z = max((scorer.z[r.item.id] for r in group.rows if r.item.id in scorer.z), default=0.0)
        card = cards.get(lead.item.id)
        metrics: dict[str, Any] = {
            **scorer.metrics.get(lead.item.id, {}),
            "basis": BASIS[lead.source_key],
            "days_active": len(days),
            "first_seen": min(_kst_day(r.item.first_seen_at) for r in group.rows).isoformat(),
        }
        if top is not None:
            metrics["best_rank"] = top
        drafts.append(
            Candidate(
                cid="",
                section="oss",
                key=f"item:{lead.item.id}",
                item_ids=[lead.item.id, *(r.item.id for r in group.rows if r is not lead)],
                title_ko=(card.title_ko if card is not None else None) or lead.item.title,
                summary_ko=_summary(card),
                url=lead.item.url,
                metrics=metrics,
                score=len(days) * 20 + max(OSS_RANK_BONUS - (top or OSS_RANK_BONUS), 0) + z,
                stat_rank=0,
                group="sustained",
            )
        )
    return drafts


def _research(session: Session, start: datetime, end: datetime) -> list[Candidate]:
    """Papers news or the community pointed at (by DOI or arXiv id) on MIN_RESEARCH_DAYS days of
    the span, or at least MIN_RESEARCH_MENTIONS times: mentions × 10 + days × 20. Listings of
    one work (arXiv and Hugging Face) fold."""
    carriers: dict[tuple[str, str], dict[int, date]] = defaultdict(dict)
    for item_id, kind, value, seen in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value, Item.first_seen_at)
        .join(Item, Item.id == ItemRef.item_id)
        .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
        .where(
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
            Item.canary.is_(False),
            Item.track.in_((Track.NEWS, Track.COMMUNITY)),
            ELIGIBLE,
            ItemRef.kind.in_(RESEARCH_REF_KINDS),
        )
    ):
        carriers[(kind, value)][item_id] = _kst_day(seen)
    if not carriers:
        return []
    values = {value for _, value in carriers}
    papers: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for item_id, kind, value in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value)
        .join(Item, Item.id == ItemRef.item_id)
        .where(
            Item.track == Track.RESEARCH_IP,
            Item.canary.is_(False),
            ItemRef.kind.in_(RESEARCH_REF_KINDS),
            ItemRef.value.in_(values),
        )
    ):
        if (kind, value) in carriers:
            papers[item_id].add((kind, value))
    if not papers:
        return []
    rows = {row.item.id: row for row in _select_rows(session, Item.id.in_(list(papers)))}
    # twins (the same work on arXiv and Hugging Face) share a reference: one candidate, the
    # first-collected listing leading
    owner: dict[tuple[str, str], int] = {}
    work: dict[int, list[int]] = defaultdict(list)
    for item_id in sorted(papers):
        if item_id not in rows:
            continue
        lead = next((owner[ref] for ref in papers[item_id] if ref in owner), item_id)
        for ref in papers[item_id]:
            owner.setdefault(ref, lead)
        work[lead].append(item_id)
    cards = _cards(session, list(work))
    drafts: list[Candidate] = []
    for lead_id, members in work.items():
        mentioned: dict[int, date] = {}
        for member in members:
            for ref in papers[member]:
                mentioned.update(carriers[ref])
        days = set(mentioned.values())
        if len(days) < MIN_RESEARCH_DAYS and len(mentioned) < MIN_RESEARCH_MENTIONS:
            continue
        paper = rows[lead_id]
        card = cards.get(lead_id)
        drafts.append(
            Candidate(
                cid="",
                section="research",
                key=f"item:{lead_id}",
                item_ids=[lead_id, *(m for m in members if m != lead_id)],
                title_ko=(card.title_ko if card is not None else None) or paper.item.title,
                summary_ko=_summary(card),
                url=paper.item.url,
                metrics={
                    "mentions": len(mentioned),
                    "days_active": len(days),
                    "first_seen": min(days).isoformat(),
                },
                score=float(len(mentioned) * 10 + len(days) * 20),
                stat_rank=0,
                group="sustained",
            )
        )
    return drafts


def _benchmark_holders(session: Session, end: datetime) -> list[Candidate]:
    """Models that held a leaderboard top-5 place through the span, one per model (its best
    board): days × 20 + (6 - rank) × 10."""
    try:
        with session.begin_nested():
            holders = top_holders(session, now=end, days=SPAN_DAYS, top=BENCHMARK_TOP)
    except Exception:  # noqa: BLE001 - the rest of the section does not depend on it
        logger.exception("spotlight: leaderboard holders unavailable for the ai section")
        return []
    best: dict[str, dict[str, Any]] = {}
    for holder in holders:
        key = model_key(holder["model"])
        if key not in best or (holder["rank"], -holder["days"]) < (
            best[key]["rank"],
            -best[key]["days"],
        ):
            best[key] = holder
    drafts: list[Candidate] = []
    for key, holder in best.items():
        where = f"{holder['site']} {holder['board']}"
        drafts.append(
            Candidate(
                cid="",
                section="ai",
                key=key,
                item_ids=[],
                title_ko=f"{holder['model']} — {where} {holder['rank']}위",
                summary_ko=(
                    f"{where} 순위표에서 {holder['days']}일 동안"
                    f" 상위 {BENCHMARK_TOP}위 안을 지켰다."
                ),
                url="",
                metrics={
                    "basis": "benchmark",
                    "site": holder["site"],
                    "board": holder["board"],
                    "rank": holder["rank"],
                    "best_rank": holder["best_rank"],
                    "days_active": holder["days"],
                    "first_seen": _kst_day(end - timedelta(days=holder["days"] - 1)).isoformat(),
                },
                score=float(holder["days"] * 20 + (BENCHMARK_TOP + 1 - holder["rank"]) * 10),
                stat_rank=0,
                group="sustained",
            )
        )
    return drafts


def _listed(session: Session, day: date) -> dict[str, list[Candidate]]:
    """What the published spotlight listed (same section and key) on MIN_LISTED_DAYS or more of
    the previous LISTED_LOOKBACK days, as its latest entry: days × 20 + (11 - best rank)."""
    rows = session.execute(
        select(Spotlight.spotlight_date, SpotlightEntry)
        .join(Spotlight, Spotlight.id == SpotlightEntry.spotlight_id)
        .where(
            Spotlight.status == SpotlightStatus.PUBLISHED,
            Spotlight.spotlight_date >= day - timedelta(days=LISTED_LOOKBACK),
            Spotlight.spotlight_date < day,
        )
        .order_by(Spotlight.spotlight_date)
    ).tuples()
    seen: dict[tuple[str, str], list[tuple[date, SpotlightEntry]]] = defaultdict(list)
    for listed_on, entry in rows:
        seen[(entry.section, entry.key)].append((listed_on, entry))
    out: dict[str, list[Candidate]] = defaultdict(list)
    for (section, key), listings in seen.items():
        days = {listed_on for listed_on, _ in listings}
        if len(days) < MIN_LISTED_DAYS or section not in SECTIONS:
            continue
        _, latest = listings[-1]
        best = min(entry.rank for _, entry in listings)
        out[section].append(
            Candidate(
                cid="",
                section=section,
                key=key,
                item_ids=list(latest.item_ids),
                title_ko=latest.title_ko,
                summary_ko=latest.summary,
                url="",
                metrics={
                    **{k: v for k, v in latest.metrics.items() if k != "group_size"},
                    "days_active": len(days),
                    "first_seen": min(days).isoformat(),
                    "listed_days": len(days),
                },
                score=float(len(days) * 20 + max(11 - best, 0)),
                stat_rank=0,
                group="sustained",
            )
        )
    return out


def _number(section: str, drafts: list[Candidate]) -> list[Candidate]:
    """Strongest first (ties keep arrival order), one per key, cut to LIMIT and numbered."""
    ranked: list[Candidate] = []
    keys: set[str] = set()
    for candidate in sorted(drafts, key=lambda c: -c.score):
        if candidate.key in keys:
            continue
        keys.add(candidate.key)
        ranked.append(candidate)
    ranked = ranked[:LIMIT]
    for rank, candidate in enumerate(ranked, start=1):
        candidate.stat_rank = rank
        candidate.cid = f"{CID_PREFIX[section]}s{rank}"
    return ranked


def collect_sustained(session: Session, *, day: date) -> dict[str, list[Candidate]]:
    """Every section's 지속 주목 candidates for the briefing `day`."""
    start, end = span(day)
    scorer = Scorer(session, at=end)
    found: dict[str, list[Candidate]] = defaultdict(list)
    for section, drafts in _story_sections(session, start, end).items():
        found[section] += drafts
    found["oss"] += _oss(session, start, end, scorer)
    found["research"] += _research(session, start, end)
    found["ai"] += _benchmark_holders(session, end)
    for section, drafts in _listed(session, day).items():
        found[section] += drafts
    return {section: _number(section, found.get(section, [])) for section in SECTIONS}
