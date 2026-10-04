"""Console read models for Korean cards (card feed and generation health)."""

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Text, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardRun, CardStatus, ItemCard
from news_insight.cards.service import pending_count
from news_insight.classify.models import ItemLabel
from news_insight.classify.store import current_labels
from news_insight.classify.taxonomy import Axis, Taxonomy, get_taxonomy
from news_insight.console.queries import _like, _offset, card_body, item_rows
from news_insight.console.schemas import (
    CardRunOut,
    CardStats,
    CardView,
    Page,
    TaxonomyNodeOut,
    TaxonomyOut,
)
from news_insight.content.models import Item
from news_insight.sources.enums import Region, Track
from news_insight.sources.models import Source

KST = ZoneInfo("Asia/Seoul")


def has_label(axis: Axis, key: str) -> Any:
    return exists().where(
        ItemLabel.item_id == Item.id,
        ItemLabel.axis == axis,
        ItemLabel.node_key == key,
        ItemLabel.superseded_at.is_(None),
    )


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
    labels: dict[Axis, str] | None = None,
) -> Page[CardView]:
    """Ready cards, newest first; `labels` keeps cards carrying every given axis key."""
    conditions = [ItemCard.status == CardStatus.READY]
    conditions.extend(has_label(axis, key) for axis, key in (labels or {}).items())
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
        select(Item, Source, ItemCard)
        .join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
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
    items = item_rows(session, [(item, source) for item, source, _ in rows])
    found = current_labels(session, [item.id for item, _, _ in rows])
    taxonomy = get_taxonomy()
    views = [
        CardView(item=row, card=card_body(card, found.get(row.id), taxonomy))
        for row, (_, _, card) in zip(items, rows, strict=True)
    ]
    return Page[CardView](items=views, total=total, page=page, size=size)


def taxonomy_out(taxonomy: Taxonomy) -> TaxonomyOut:
    def nodes(axis: Axis) -> list[TaxonomyNodeOut]:
        return [
            TaxonomyNodeOut(key=node.key, label=node.label, description=node.description)
            for node in taxonomy.nodes(axis)
        ]

    return TaxonomyOut(
        revision=taxonomy.revision,
        max_fields=taxonomy.max_labels(Axis.FIELD),
        max_products=taxonomy.max_labels(Axis.PRODUCT),
        fields=nodes(Axis.FIELD),
        products=nodes(Axis.PRODUCT),
        impacts=nodes(Axis.IMPACT),
    )


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
    last = session.scalars(select(CardRun).order_by(CardRun.id.desc()).limit(1)).first()
    return CardStats(
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
