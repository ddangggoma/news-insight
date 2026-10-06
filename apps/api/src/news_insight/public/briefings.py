"""Published daily briefings for readers (P6–P8): shortlist by track, digest, personas, strategy.

Only PUBLISHED versions are visible; blocked versions and gate details stay in the console.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.audio import render as audio_render
from news_insight.briefing.models import Briefing, BriefingStatus
from news_insight.briefing.service import current_briefing, failing
from news_insight.briefing.strength import Strength, evidence_for, grade
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.companies.catalog import ORGANIZATIONS, CompanyKind
from news_insight.companies.service import info_for
from news_insight.config import get_settings
from news_insight.console.briefings import strategy_out
from news_insight.console.queries import latest_metrics
from news_insight.content.models import Item
from news_insight.digest.bundle import digest_window
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestContent, DigestItemRef, Insight, TrackSection
from news_insight.public.feed import _reader_item, company_refs
from news_insight.public.periodic import PeriodicEntry
from news_insight.public.periodic import recent as periodic_recent
from news_insight.public.periods import KST
from news_insight.public.schemas import ReaderItem
from news_insight.signals import service as radar_signals
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.strategy.models import StrategyRun
from news_insight.strategy.personas import DEFAULT_PERSONA
from news_insight.watchlist import service as watchlist
from news_insight.watchlist.service import WatchHit

TRACK_ORDER = ("news", "research_ip", "oss", "community")


class BriefingSection(BaseModel):
    track: str
    summary: str | None
    items: list[ReaderItem]


class BriefingPersona(BaseModel):
    key: str
    name: str
    group: str
    status: str
    headline: str
    insight: str
    actions: list[str]
    item_ids: list[int]
    relevance: int = 0
    stances: list[dict[str, str]] = []


class StanceConflict(BaseModel):
    """A theme some roles read as an opportunity and others as a risk (plan 13 B6)."""

    theme: str
    opportunity: list[str]
    risk: list[str]


class BriefingStrategy(BaseModel):
    personas: list[BriefingPersona]
    default_persona: str = DEFAULT_PERSONA
    conflicts: list[StanceConflict] = []
    report: dict[str, Any] | None
    review_verdict: str | None
    dropped_claims: int


class BriefingSignal(BaseModel):
    """A radar card stored for the briefing date (PRD-1), linked to the radar."""

    tone: str
    title: str
    detail: str
    window_key: str
    is_current: bool
    href: str


class BriefingAudio(BaseModel):
    url: str
    seconds: int


class BriefingInsight(Insight):
    strength: Strength | None = None


class ContinuingStory(BaseModel):
    """A story in today's shortlist that has been reported on more than one day."""

    story_id: int
    item_id: int
    title: str
    days: int
    sources: int


class CompanyMove(BaseModel):
    """A registered company named in today's shortlist (plan 12, plan 13 B4)."""

    key: str
    label: str
    relation: str
    kind: str
    count: int
    item_ids: list[int]


class PublicBriefing(BaseModel):
    briefing_date: date
    version: int
    published_at: datetime
    headline: str | None
    tldr: list[str] = []
    overview: str | None
    insights: list[BriefingInsight]
    continuing: list[ContinuingStory] = []
    companies: list[CompanyMove] = []
    # the whole-collection summary by track and category (the digest page, plan 13 C2)
    digest_tracks: list[TrackSection] = []
    # the reader's watched companies, themes and keywords in the briefing day (plan 13 A5)
    watch: list[WatchHit] = []
    # the spoken version, when the host has rendered it (plan 13 A1)
    audio: BriefingAudio | None = None
    # the newest weekly and monthly briefings, linked from the aside (plan 13 C4)
    periodic: list[PeriodicEntry] = []
    sections: list[BriefingSection]
    strategy: BriefingStrategy | None
    signals: list[BriefingSignal] = []
    refs: list[DigestItemRef]
    gates_passed: int
    gates_total: int
    previous_date: date | None
    next_date: date | None


class BriefingEntry(BaseModel):
    briefing_date: date
    version: int
    headline: str | None
    items: int
    published_at: datetime


def published(session: Session, briefing_date: date | None = None) -> Briefing | None:
    """The current briefing, or the newest published version for a date."""
    if briefing_date is None:
        return current_briefing(session)
    return session.scalars(
        select(Briefing)
        .where(Briefing.briefing_date == briefing_date, Briefing.status == BriefingStatus.PUBLISHED)
        .order_by(Briefing.version.desc())
        .limit(1)
    ).first()


def _neighbour(session: Session, day: date, *, later: bool) -> date | None:
    column = Briefing.briefing_date
    return session.scalar(
        select(func.min(column) if later else func.max(column)).where(
            Briefing.status == BriefingStatus.PUBLISHED, column > day if later else column < day
        )
    )


def _items(session: Session, item_ids: list[int]) -> dict[int, ReaderItem]:
    """Reader rows for the frozen shortlist (any taxonomy revision: briefings are immutable)."""
    if not item_ids:
        return {}
    rows = list(
        session.execute(
            select(Item, Source, ItemCard, Story)
            .join(Source, Source.id == Item.source_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(StoryItem, StoryItem.item_id == Item.id)
            .outerjoin(Story, Story.id == StoryItem.story_id)
            .where(Item.id.in_(item_ids), ItemCard.status == CardStatus.READY)
        ).tuples()
    )
    metrics = latest_metrics(session, [item.id for item, *_ in rows])
    names = company_refs(session, [card for _, _, card, _ in rows])
    return {
        item.id: _reader_item(item, source, card, story, metrics.get(item.id, {}), names)
        for item, source, card, story in rows
    }


def _audio(briefing: Briefing) -> BriefingAudio | None:
    recorded = audio_render.entry_for(
        get_settings().media_dir, briefing.briefing_date.isoformat(), briefing.version
    )
    return BriefingAudio(url=recorded.url, seconds=recorded.seconds) if recorded else None


def _refs(session: Session, item_ids: set[int]) -> list[DigestItemRef]:
    if not item_ids:
        return []
    return [
        DigestItemRef(
            id=item.id, title=item.title, url=item.url, source_name=source.name, track=item.track
        )
        for item, source in session.execute(
            select(Item, Source)
            .join(Source, Source.id == Item.source_id)
            .where(Item.id.in_(item_ids))
        ).tuples()
    ]


def public_briefing(session: Session, briefing: Briefing) -> PublicBriefing:
    freeze_window = digest_window(briefing.briefing_date)
    digest = session.get(Digest, briefing.digest_id) if briefing.digest_id else None
    content = DigestContent.model_validate(digest.content) if digest is not None else None
    items = _items(session, [int(entry["item_id"]) for entry in briefing.shortlist])
    by_track: dict[str, list[ReaderItem]] = {}
    for entry in briefing.shortlist:
        row = items.get(int(entry["item_id"]))
        if row is not None:
            by_track.setdefault(str(entry["track"]), []).append(row)
    summaries = {t.track.value: t.summary for t in content.tracks} if content else {}
    order = [*TRACK_ORDER, *(t for t in by_track if t not in TRACK_ORDER)]
    sections = [
        BriefingSection(track=track, summary=summaries.get(track), items=by_track[track])
        for track in order
        if track in by_track
    ]
    cited: set[int] = {
        i for insight in (content.insights if content else []) for i in insight.item_ids
    }
    # the whole-collection summary links its points too (plan 13 C2)
    cited.update(
        i
        for track in (content.tracks if content else [])
        for category in track.categories
        for point in category.points
        for i in point.item_ids
    )
    strategy = None
    run = session.get(StrategyRun, briefing.strategy_id) if briefing.strategy_id else None
    if run is not None:
        full = strategy_out(session, run)
        personas = [BriefingPersona.model_validate(p.model_dump()) for p in full.personas]
        strategy = BriefingStrategy(
            personas=personas,
            conflicts=stance_conflicts(personas),
            report=full.report,
            review_verdict=str(full.review.get("verdict")) if full.review else None,
            dropped_claims=full.dropped_claims,
        )
        cited.update(ref.id for ref in full.items)
    blocking = [gate for gate in briefing.gates if gate.get("blocking", True)]
    insights = content.insights if content else []
    report = strategy.report if strategy is not None else None
    evidence = evidence_for(
        session,
        [i for insight in insights for i in insight.item_ids] + _report_ids(report),
    )
    if report is not None:
        _grade_report(report, evidence)
    shortlist_ids = [int(entry["item_id"]) for entry in briefing.shortlist]
    watch = watchlist.hits(session, start=freeze_window[0], end=freeze_window[1])
    cited.update(i for hit in watch for i in hit.item_ids)
    return PublicBriefing(
        briefing_date=briefing.briefing_date,
        version=briefing.version,
        published_at=briefing.published_at,
        headline=content.headline if content else None,
        tldr=content.tldr if content else [],
        overview=content.overview if content else None,
        insights=[
            BriefingInsight(**insight.model_dump(), strength=grade(insight.item_ids, evidence))
            for insight in insights
        ],
        continuing=continuing_stories(session, shortlist_ids),
        companies=company_moves(session, shortlist_ids),
        digest_tracks=content.tracks if content else [],
        watch=watch,
        audio=_audio(briefing),
        periodic=periodic_recent(session, limit=3),
        sections=sections,
        strategy=strategy,
        signals=[
            BriefingSignal(
                tone=row.tone,
                title=row.title,
                detail=row.detail,
                window_key=row.window_key,
                is_current=row.is_current,
                href=radar_signals.radar_path(row),
            )
            for row in radar_signals.for_day(session, briefing.briefing_date)
        ],
        refs=_refs(session, cited),
        gates_passed=len(blocking) - len(failing(blocking)),
        gates_total=len(blocking),
        previous_date=_neighbour(session, briefing.briefing_date, later=False),
        next_date=_neighbour(session, briefing.briefing_date, later=True),
    )


def archive(session: Session, *, page: int, size: int) -> tuple[list[BriefingEntry], int]:
    latest = (
        select(Briefing.briefing_date, func.max(Briefing.version).label("version"))
        .where(Briefing.status == BriefingStatus.PUBLISHED)
        .group_by(Briefing.briefing_date)
        .subquery()
    )
    total = session.scalar(select(func.count()).select_from(latest)) or 0
    rows = session.execute(
        select(Briefing, Digest.content["headline"].astext)
        .join(
            latest,
            (latest.c.briefing_date == Briefing.briefing_date)
            & (latest.c.version == Briefing.version),
        )
        .outerjoin(Digest, Digest.id == Briefing.digest_id)
        .order_by(Briefing.briefing_date.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).tuples()
    entries = [
        BriefingEntry(
            briefing_date=briefing.briefing_date,
            version=briefing.version,
            headline=headline,
            items=len(briefing.shortlist),
            published_at=briefing.published_at,
        )
        for briefing, headline in rows
    ]
    return entries, total


CONTINUING_TOP = 5
COMPANY_TOP = 8
RELATION_ORDER = {"competitor": 0, "self": 1, "supplier": 2, "partner": 3, "peer": 4}


def continuing_stories(session: Session, item_ids: list[int]) -> list[ContinuingStory]:
    """Shortlisted stories reported on two or more KST days, longest running first."""
    if not item_ids:
        return []
    rows = session.execute(
        select(StoryItem.item_id, Story, ItemCard.title_ko, Item.title)
        .join(Story, Story.id == StoryItem.story_id)
        .join(Item, Item.id == StoryItem.item_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(StoryItem.item_id.in_(item_ids))
    ).tuples()
    found: dict[int, ContinuingStory] = {}
    for item_id, story, title_ko, title in rows:
        first = story.first_seen_at.astimezone(KST).date()
        last = story.last_seen_at.astimezone(KST).date()
        days = (last - first).days + 1
        if days < 2 or story.id in found:
            continue
        found[story.id] = ContinuingStory(
            story_id=story.id,
            item_id=int(item_id),
            title=story.title_ko or title_ko or title,
            days=days,
            sources=story.source_count,
        )
    return sorted(found.values(), key=lambda s: (-s.days, -s.sources, s.story_id))[:CONTINUING_TOP]


def company_moves(session: Session, item_ids: list[int]) -> list[CompanyMove]:
    """Registered companies (not institutes or regulators) in the shortlist, most named first."""
    if not item_ids:
        return []
    order = {item_id: index for index, item_id in enumerate(item_ids)}
    rows = session.execute(
        select(ItemCard.item_id, ItemCard.company_keys).where(ItemCard.item_id.in_(item_ids))
    ).tuples()
    named: dict[str, list[int]] = {}
    for item_id, keys in sorted(rows, key=lambda row: order.get(int(row[0]), 0)):
        for key in keys or []:
            named.setdefault(str(key), []).append(int(item_id))
    registry = info_for(session, named)
    moves = [
        CompanyMove(
            key=key,
            label=info.name_ko or info.name,
            relation=info.relation,
            kind=info.kind,
            count=len(named[key]),
            item_ids=named[key][:3],
        )
        for key, info in registry.items()
        if CompanyKind(info.kind) not in ORGANIZATIONS
    ]
    moves.sort(key=lambda m: (-m.count, RELATION_ORDER.get(m.relation, 9), m.key))
    return moves[:COMPANY_TOP]


def _claims(report: dict[str, Any]) -> list[dict[str, Any]]:
    claims = [c for section in report.get("fields", []) for c in section.get("claims", [])]
    for group in ("roadmap", "opportunities", "risks"):
        claims += list(report.get(group, []))
    return [c for c in claims if isinstance(c, dict)]


def _report_ids(report: dict[str, Any] | None) -> list[int]:
    return [int(i) for c in _claims(report or {}) for i in c.get("item_ids", [])]


def _grade_report(report: dict[str, Any], evidence: dict[int, Any]) -> None:
    """Add a `strength` to every strategy claim (plan 13 B2)."""
    for claim in _claims(report):
        strength = grade([int(i) for i in claim.get("item_ids", [])], evidence)
        claim["strength"] = strength.model_dump() if strength else None


def stance_conflicts(personas: list[BriefingPersona]) -> list[StanceConflict]:
    """Themes read as an opportunity by some roles and as a risk by others, widest split first."""
    by_theme: dict[str, dict[str, list[str]]] = {}
    for persona in personas:
        if persona.status != "insight":
            continue
        for entry in persona.stances:
            side = by_theme.setdefault(entry["theme"], {"opportunity": [], "risk": []})
            if entry["stance"] in side:
                side[entry["stance"]].append(persona.name)
    conflicts = [
        StanceConflict(theme=theme, opportunity=sides["opportunity"], risk=sides["risk"])
        for theme, sides in by_theme.items()
        if sides["opportunity"] and sides["risk"]
    ]
    conflicts.sort(key=lambda c: (-min(len(c.opportunity), len(c.risk)), c.theme))
    return conflicts[:5]
