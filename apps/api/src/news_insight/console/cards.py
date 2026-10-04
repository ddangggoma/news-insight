"""Console read models for Korean cards (card feed and generation health)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Text, cast, func, literal_column, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.cards.service import pending_count
from news_insight.console.queries import _like, _offset, card_body, item_rows
from news_insight.console.schemas import (
    CardFailure,
    CardRunOut,
    CardStats,
    CardView,
    Page,
    StoryRef,
)
from news_insight.content.models import Item
from news_insight.sources.enums import Region, Track
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem

KST = ZoneInfo("Asia/Seoul")


def list_cards(
    session: Session,
    *,
    track: Track | None,
    category: str | None,
    region: Region | None,
    days: int | None,
    q: str | None,
    page: int,
    size: int,
    now: datetime,
    field: str | None = None,
    business: str | None = None,
    impact: str | None = None,
    scope: str | None = None,
    dedup: bool = False,
) -> Page[CardView]:
    conditions = [ItemCard.status == CardStatus.READY]
    if field:
        conditions.append(ItemCard.field == field)
    if business:
        conditions.append(ItemCard.businesses.contains([business]))
    if impact:
        conditions.append(ItemCard.impact == impact)
    if scope == "relevant":
        conditions.append(ItemCard.scope.in_(["dx", "dx_dependency"]))
    elif scope:
        conditions.append(ItemCard.scope == scope)
    if dedup:
        # one card per story: its representative, plus items not clustered yet
        conditions.append(
            or_(
                StoryItem.item_id.is_(None),
                Story.representative_item_id == Item.id,
            )
        )
    if track is not None:
        conditions.append(Item.track == track)
    if category:
        conditions.append(Source.category == category)
    if region is not None:
        conditions.append(Source.region == region)
    if days:
        conditions.append(Item.first_seen_at >= now - timedelta(days=days))
    if q:
        pattern = _like(q)
        conditions.append(
            or_(
                ItemCard.title_ko.ilike(pattern, escape="\\"),
                Item.title.ilike(pattern, escape="\\"),
                cast(ItemCard.keywords, Text).ilike(pattern, escape="\\"),
            )
        )
    base = (
        select(Item, Source, ItemCard, Story)
        .join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(Story, Story.id == StoryItem.story_id)
        .where(*conditions)
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        session.execute(
            base.order_by(
                Item.first_seen_at.desc(), Item.published_at.desc().nulls_last(), Item.id.desc()
            )
            .offset(_offset(page, size))
            .limit(size)
        ).tuples()
    )
    items = item_rows(session, [(item, source) for item, source, _, _ in rows])
    views = [
        CardView(
            item=row,
            card=card_body(card),
            story=StoryRef(
                id=story.id,
                item_count=story.item_count,
                source_count=story.source_count,
                tracks=list(story.tracks),
                is_representative=story.representative_item_id == row.id,
            )
            if story is not None
            else None,
        )
        for row, (_, _, card, story) in zip(items, rows, strict=True)
    ]
    return Page[CardView](items=views, total=total, page=page, size=size)


def card_stats(session: Session, *, now: datetime) -> CardStats:
    counts = dict(
        session.execute(select(ItemCard.status, func.count()).group_by(ItemCard.status))
        .tuples()
        .all()
    )
    today = datetime.combine(now.astimezone(KST).date(), time(0, 0), tzinfo=KST)
    ready_today = session.scalar(
        select(func.count())
        .select_from(ItemCard)
        .where(ItemCard.status == CardStatus.READY, ItemCard.generated_at >= today)
    )
    by_engine = dict(
        session.execute(
            select(ItemCard.engine, func.count())
            .where(ItemCard.status == CardStatus.READY)
            .group_by(ItemCard.engine)
        )
        .tuples()
        .all()
    )
    week = now - timedelta(days=7)
    recent = dict(
        session.execute(
            select(ItemCard.status, func.count())
            .where(ItemCard.generated_at >= week)
            .group_by(ItemCard.status)
        )
        .tuples()
        .all()
    )
    ok, bad = recent.get(CardStatus.READY, 0), recent.get(CardStatus.FAILED, 0)
    scope_key = func.coalesce(ItemCard.scope, literal_column("'unclassified'"))
    scope = dict(
        session.execute(
            select(scope_key, func.count())
            .where(ItemCard.generated_at >= week, ItemCard.status == CardStatus.READY)
            .group_by(scope_key)
        )
        .tuples()
        .all()
    )
    last = session.scalars(select(CardRun).order_by(CardRun.id.desc()).limit(1)).first()
    return CardStats(
        success_rate_7d=ok / (ok + bad) if ok + bad else None,
        scope_7d={str(key): int(value) for key, value in scope.items()},
        ready=counts.get(CardStatus.READY, 0),
        failed=counts.get(CardStatus.FAILED, 0),
        pending=pending_count(session),
        ready_today=ready_today or 0,
        by_engine={str(engine): count for engine, count in by_engine.items() if engine},
        last_run=CardRunOut(
            started_at=last.started_at,
            finished_at=last.finished_at,
            ready=last.ready,
            failed=last.failed,
            batches=dict(last.batches),
            quota=dict(last.quota),
            note=last.note,
        )
        if last
        else None,
    )


def card_failures(session: Session, *, limit: int) -> list[CardFailure]:
    rows = list(
        session.execute(
            select(Item, Source, ItemCard)
            .join(Source, Source.id == Item.source_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .where(ItemCard.status == CardStatus.FAILED)
            .order_by(ItemCard.generated_at.desc())
            .limit(limit)
        ).tuples()
    )
    items = item_rows(session, [(item, source) for item, source, _ in rows])
    return [
        CardFailure(
            item=row, error=card.error, attempts=card.attempts, generated_at=card.generated_at
        )
        for row, (_, _, card) in zip(items, rows, strict=True)
    ]
