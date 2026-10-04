"""Published daily briefings for readers (P6–P8): shortlist by track, digest, personas, strategy.

Only PUBLISHED versions are visible; blocked versions and gate details stay in the console.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingStatus
from news_insight.briefing.service import current_briefing, failing
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.console.briefings import strategy_out
from news_insight.console.queries import latest_metrics
from news_insight.content.models import Item
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestContent, DigestItemRef, Insight
from news_insight.public.feed import _reader_item
from news_insight.public.schemas import ReaderItem
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.strategy.models import StrategyRun

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


class BriefingStrategy(BaseModel):
    personas: list[BriefingPersona]
    report: dict[str, Any] | None
    review_verdict: str | None
    dropped_claims: int


class PublicBriefing(BaseModel):
    briefing_date: date
    version: int
    published_at: datetime
    headline: str | None
    overview: str | None
    insights: list[Insight]
    sections: list[BriefingSection]
    strategy: BriefingStrategy | None
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
    return {
        item.id: _reader_item(item, source, card, story, metrics.get(item.id, {}))
        for item, source, card, story in rows
    }


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
    strategy = None
    run = session.get(StrategyRun, briefing.strategy_id) if briefing.strategy_id else None
    if run is not None:
        full = strategy_out(session, run)
        strategy = BriefingStrategy(
            personas=[BriefingPersona.model_validate(p.model_dump()) for p in full.personas],
            report=full.report,
            review_verdict=str(full.review.get("verdict")) if full.review else None,
            dropped_claims=full.dropped_claims,
        )
        cited.update(ref.id for ref in full.items)
    blocking = [gate for gate in briefing.gates if gate.get("blocking", True)]
    return PublicBriefing(
        briefing_date=briefing.briefing_date,
        version=briefing.version,
        published_at=briefing.published_at,
        headline=content.headline if content else None,
        overview=content.overview if content else None,
        insights=content.insights if content else [],
        sections=sections,
        strategy=strategy,
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
