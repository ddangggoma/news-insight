"""Reader feed (one row per story) and item detail."""

from collections.abc import Sequence
from typing import Literal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.companies.service import info_for
from news_insight.console.queries import latest_metrics
from news_insight.content.models import Item
from news_insight.public.filters import ReaderFilters, in_current_tree, in_window, joined
from news_insight.public.periods import Window
from news_insight.public.schemas import (
    CompanyRef,
    FeedPage,
    LinkedItem,
    ReaderItem,
    ReaderItemDetail,
    StoryBrief,
)
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef, Story, StoryItem

Sort = Literal["recent", "relevance", "coverage"]


def company_refs(session: Session, cards: Sequence[ItemCard]) -> dict[str, CompanyRef]:
    """Registry names of the companies on these cards (one query per page)."""
    keys = {key for card in cards for key in card.company_keys or []}
    return {
        key: CompanyRef(
            key=key, label=info.name_ko or info.name, relation=info.relation, kind=info.kind
        )
        for key, info in info_for(session, keys).items()
    }


def _reader_item(
    item: Item,
    source: Source,
    card: ItemCard,
    story: Story | None,
    metrics: dict[str, int],
    companies: dict[str, CompanyRef] | None = None,
) -> ReaderItem:
    return ReaderItem(
        id=item.id,
        url=item.url,
        title=item.title,
        title_ko=card.title_ko,
        summary_ko=list(card.summary_ko),
        keywords=list(card.keywords),
        field=card.field,
        themes=list(card.themes or []),
        signal_type=card.signal_type,
        impact=card.impact,
        scope=card.scope,
        relevance=card.relevance,
        track=item.track.value,
        source_name=source.name,
        region=source.region.value,
        published_at=item.published_at,
        first_seen_at=item.first_seen_at,
        metrics=metrics,
        story=StoryBrief(
            id=story.id,
            item_count=story.item_count,
            source_count=story.source_count,
            tracks=list(story.tracks),
        )
        if story is not None
        else None,
        companies=[companies[k] for k in card.company_keys or [] if companies and k in companies],
    )


def feed(
    session: Session,
    filters: ReaderFilters,
    window: Window,
    *,
    sort: Sort,
    page: int,
    size: int,
    extra: Sequence[ColumnElement[bool]] = (),
) -> FeedPage:
    # One row per story: the best matching report (the representative first, then the newest),
    # so a story stays visible when only a follow-up report matches the filters.
    ranked = joined(
        select(
            Item.id.label("item_id"),
            func.row_number()
            .over(
                partition_by=func.coalesce(StoryItem.story_id, -Item.id),
                order_by=(
                    (Story.representative_item_id == Item.id).desc().nulls_last(),
                    Item.first_seen_at.desc(),
                ),
            )
            .label("rank"),
        )
    ).where(*filters.conditions(), *in_window(window), *extra)
    ranked_rows = ranked.subquery()
    picked = select(ranked_rows.c.item_id).where(ranked_rows.c.rank == 1)
    total = session.scalar(select(func.count()).select_from(picked.subquery())) or 0
    items_total = session.scalar(select(func.count()).select_from(ranked_rows)) or 0
    order = {
        "recent": (Item.first_seen_at.desc(), Item.id.desc()),
        "relevance": (
            ItemCard.relevance.desc().nulls_last(),
            Item.first_seen_at.desc(),
            Item.id.desc(),
        ),
        "coverage": (
            func.coalesce(Story.source_count, 1).desc(),
            Item.first_seen_at.desc(),
            Item.id.desc(),
        ),
    }[sort]
    rows = list(
        session.execute(
            joined(select(Item, Source, ItemCard, Story))
            .where(Item.id.in_(picked))
            .order_by(*order)
            .offset((page - 1) * size)
            .limit(size)
        ).tuples()
    )
    metrics = latest_metrics(session, [item.id for item, *_ in rows])
    names = company_refs(session, [card for _, _, card, _ in rows])
    return FeedPage(
        items=[
            _reader_item(item, source, card, story, metrics.get(item.id, {}), names)
            for item, source, card, story in rows
        ],
        total=total,
        items_total=items_total,
        page=page,
        size=size,
    )


def _published(session: Session, item_ids: list[int]) -> list[tuple[Item, Source, ItemCard]]:
    if not item_ids:
        return []
    return list(
        session.execute(
            select(Item, Source, ItemCard)
            .join(Source, Source.id == Item.source_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .where(
                Item.id.in_(item_ids),
                ItemCard.status == CardStatus.READY,
                in_current_tree(),
            )
            .order_by(Item.first_seen_at.desc(), Item.id.desc())
        ).tuples()
    )


def _linked(item: Item, source: Source, card: ItemCard, ref: str | None = None) -> LinkedItem:
    return LinkedItem(
        id=item.id,
        url=item.url,
        title=item.title,
        title_ko=card.title_ko,
        track=item.track.value,
        source_name=source.name,
        first_seen_at=item.first_seen_at,
        ref=ref,
    )


def item_detail(session: Session, item_id: int) -> ReaderItemDetail | None:
    row = (
        session.execute(
            joined(select(Item, Source, ItemCard, Story)).where(
                Item.id == item_id,
                ItemCard.status == CardStatus.READY,
                in_current_tree(),
            )
        )
        .tuples()
        .first()
    )
    if row is None:
        return None
    item, source, card, story = row
    metrics = latest_metrics(session, [item.id]).get(item.id, {})

    story_items: list[LinkedItem] = []
    if story is not None:
        member_ids = list(
            session.scalars(
                select(StoryItem.item_id).where(
                    StoryItem.story_id == story.id, StoryItem.item_id != item.id
                )
            )
        )
        story_items = [_linked(*linked) for linked in _published(session, member_ids)]

    refs = list(
        session.execute(select(ItemRef.kind, ItemRef.value).where(ItemRef.item_id == item.id))
    )
    signals: list[LinkedItem] = []
    for kind, value in refs:
        partner_ids = list(
            session.scalars(
                select(ItemRef.item_id).where(
                    ItemRef.kind == kind, ItemRef.value == value, ItemRef.item_id != item.id
                )
            )
        )
        signals.extend(
            _linked(*linked, ref=f"{kind}:{value}") for linked in _published(session, partner_ids)
        )

    same_field: list[LinkedItem] = []
    if card.field:
        same_ids = list(
            session.scalars(
                select(Item.id)
                .join(ItemCard, ItemCard.item_id == Item.id)
                .where(
                    ItemCard.field == card.field,
                    ItemCard.status == CardStatus.READY,
                    in_current_tree(),
                    ItemCard.scope.in_(("dx", "dx_dependency")),
                    Item.id != item.id,
                )
                .order_by(Item.first_seen_at.desc())
                .limit(4)
            )
        )
        same_field = [_linked(*linked) for linked in _published(session, same_ids)]

    return ReaderItemDetail(
        item=_reader_item(item, source, card, story, metrics, company_refs(session, [card])),
        story_items=story_items,
        signals=signals,
        same_field=same_field,
    )
