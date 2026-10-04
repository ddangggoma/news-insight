"""Console read models for issue stories and cross-track signal chains."""

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.console.queries import _offset, card_body, item_rows
from news_insight.console.schemas import CardBody, ItemRow, Page
from news_insight.content.models import Item
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.stories.models import ItemRef, Story, StoryItem

TRACK_ORDER = {"research_ip": 0, "oss": 1, "community": 2, "news": 3}
MEMBER_LIMIT = 12


class StoryMember(BaseModel):
    item: ItemRow
    relation: str
    similarity: float | None


class StoryView(BaseModel):
    id: int
    title_ko: str | None
    item_count: int
    source_count: int
    tracks: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    max_relevance: int | None
    representative: ItemRow
    card: CardBody | None
    members: list[StoryMember]


class SignalChain(BaseModel):
    kind: str
    value: str
    tracks: list[str]
    items: list[ItemRow]


def _members(session: Session, story_ids: list[int]) -> dict[int, list[StoryMember]]:
    rows = list(
        session.execute(
            select(StoryItem, Item, Source)
            .join(Item, Item.id == StoryItem.item_id)
            .join(Source, Source.id == Item.source_id)
            .where(StoryItem.story_id.in_(story_ids))
            .order_by(StoryItem.story_id, Item.first_seen_at)
        ).tuples()
    )
    rendered = item_rows(session, [(item, source) for _, item, source in rows])
    out: dict[int, list[StoryMember]] = {}
    for (link, _, _), row in zip(rows, rendered, strict=True):
        bucket = out.setdefault(link.story_id, [])
        if len(bucket) < MEMBER_LIMIT:
            bucket.append(
                StoryMember(item=row, relation=link.relation.value, similarity=link.similarity)
            )
    return out


def list_stories(
    session: Session,
    *,
    days: int,
    min_size: int,
    min_tracks: int,
    track: Track | None,
    signal_type: str | None,
    page: int,
    size: int,
    now: datetime,
) -> Page[StoryView]:
    conditions = [
        Story.last_seen_at >= now - timedelta(days=days),
        Story.item_count >= min_size,
        func.jsonb_array_length(Story.tracks) >= min_tracks,
    ]
    if track is not None:
        conditions.append(Story.tracks.contains([track.value]))
    if signal_type:
        conditions.append(ItemCard.signal_type == signal_type)
    base = (
        select(Story, Item, Source, ItemCard)
        .join(Item, Item.id == Story.representative_item_id)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, ItemCard.item_id == Item.id)
        .where(*conditions)
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        session.execute(
            base.order_by(
                Story.source_count.desc(),
                Story.item_count.desc(),
                Story.max_relevance.desc().nulls_last(),
                Story.last_seen_at.desc(),
            )
            .offset(_offset(page, size))
            .limit(size)
        ).tuples()
    )
    reps = item_rows(session, [(item, source) for _, item, source, _ in rows])
    members = _members(session, [story.id for story, _, _, _ in rows])
    views = [
        StoryView(
            id=story.id,
            title_ko=story.title_ko,
            item_count=story.item_count,
            source_count=story.source_count,
            tracks=list(story.tracks),
            first_seen_at=story.first_seen_at,
            last_seen_at=story.last_seen_at,
            max_relevance=story.max_relevance,
            representative=rep,
            card=card_body(card) if card is not None else None,
            members=members.get(story.id, []),
        )
        for rep, (story, _, _, card) in zip(reps, rows, strict=True)
    ]
    return Page[StoryView](items=views, total=total, page=page, size=size)


def list_signals(session: Session, *, days: int, now: datetime, limit: int) -> list[SignalChain]:
    """Identifiers (arXiv id, DOI, GitHub repo) shared by items from two or more tracks."""
    since = now - timedelta(days=days)
    shared = (
        select(ItemRef.kind, ItemRef.value)
        .join(Item, Item.id == ItemRef.item_id)
        .where(Item.first_seen_at >= since)
        .group_by(ItemRef.kind, ItemRef.value)
        .having(func.count(func.distinct(Item.track)) >= 2)
        .order_by(func.count().desc(), func.max(Item.first_seen_at).desc())
        .limit(limit)
    )
    keys = list(session.execute(shared).tuples())
    chains: list[SignalChain] = []
    for kind, value in keys:
        pairs = list(
            session.execute(
                select(Item, Source)
                .join(Source, Source.id == Item.source_id)
                .join(ItemRef, ItemRef.item_id == Item.id)
                .where(ItemRef.kind == kind, ItemRef.value == value)
            ).tuples()
        )
        pairs.sort(key=lambda pair: (TRACK_ORDER[pair[0].track.value], pair[0].first_seen_at))
        rows = item_rows(session, pairs)
        tracks = list(dict.fromkeys(row.track.value for row in rows))
        chains.append(SignalChain(kind=kind, value=value, tracks=tracks, items=rows))
    return chains
