"""Incremental story clustering: exact duplicate → near duplicate → same event.

Items join a story once their Korean card is ready (the card title is the shared text).
Candidates come from LSH bands of items seen in the last WINDOW; nothing older is rescanned.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import array, insert
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.sources.models import Source
from news_insight.stories.minhash import (
    band_hashes,
    dedup_url,
    shingles,
    signature,
    similarity,
)
from news_insight.stories.models import ItemLsh, ItemRef, ItemSignature, Relation, Story, StoryItem
from news_insight.stories.refs import extract_refs

WINDOW = timedelta(hours=72)
EVENT_MAX_GAP = timedelta(days=2)
EVENT_CANDIDATES = 300
SessionScope = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True)
class Thresholds:
    # tuned 2026-10-04 with `stories eval` (200 LLM-judged production pairs): precision is
    # flat (~0.83) across 0.3-0.8 while recall at 0.6 was 0.41 vs 0.81 at 0.45
    near: float = 0.45
    event: float = 0.35


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class ClusterStats:
    processed: int = 0
    by_relation: dict[str, int] = field(default_factory=dict)
    refs: int = 0


def pending(session: Session, *, limit: int) -> list[tuple[Item, Source, ItemCard]]:
    statement = (
        select(Item, Source, ItemCard)
        .join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .where(ItemCard.status == CardStatus.READY, StoryItem.item_id.is_(None))
        .order_by(Item.first_seen_at, Item.id)
        .limit(limit)
    )
    return list(session.execute(statement).tuples())


def _when(item: Item) -> datetime:
    return item.published_at or item.first_seen_at


def _attach(session: Session, story: Story, item: Item, card: ItemCard, now: datetime) -> None:
    story.item_count += 1
    story.last_seen_at = max(story.last_seen_at, item.first_seen_at)
    if item.track.value not in story.tracks:
        story.tracks = [*story.tracks, item.track.value]
    relevance = card.relevance or 0
    if relevance > (story.max_relevance or -1):
        story.max_relevance = relevance
        story.representative_item_id = item.id
        story.title_ko = card.title_ko
    # distinct publishers, not catalog sources: many HN/Naver query sources share one site
    story.source_count = (
        session.scalar(
            select(func.count(func.distinct(Source.official_domain)))
            .select_from(Item)
            .join(Source, Source.id == Item.source_id)
            .join(StoryItem, StoryItem.item_id == Item.id)
            .where(StoryItem.story_id == story.id)
        )
        or 1
    )


def assign(
    session: Session,
    item: Item,
    source: Source,
    card: ItemCard,
    *,
    now: datetime,
    thresholds: Thresholds,
) -> tuple[Relation, int]:
    since = now - WINDOW
    key = dedup_url(item.url)
    sig = signature(shingles(card.title_ko or item.title))
    bands = band_hashes(sig)

    # two indexed lookups: one OR across two tables made every item scan item_signatures
    # (2026-10-05: 675 million rows read)
    exact = session.execute(
        select(StoryItem.story_id)
        .join(ItemSignature, ItemSignature.item_id == StoryItem.item_id)
        .join(Item, Item.id == StoryItem.item_id)
        .where(ItemSignature.dedup_key == key, Item.first_seen_at >= since)
        .limit(1)
    ).scalar_one_or_none()
    if exact is None:
        exact = session.execute(
            select(StoryItem.story_id)
            .join(Item, Item.id == StoryItem.item_id)
            .where(Item.content_hash == item.content_hash, Item.first_seen_at >= since)
            .limit(1)
        ).scalar_one_or_none()
    if exact is None and len(item.title.strip()) >= SAME_TITLE_MIN:
        # the same original headline elsewhere: MinHash compares Korean card titles, and two
        # translations of one headline can differ enough to split it (2026-10-05: 500 titles)
        exact = session.execute(
            select(StoryItem.story_id)
            .join(Item, Item.id == StoryItem.item_id)
            .where(
                func.lower(Item.title) == item.title.lower(),
                Item.first_seen_at >= since,
                Item.id != item.id,
            )
            .limit(1)
        ).scalar_one_or_none()

    relation, story_id, best = Relation.SEED, None, None
    if exact is not None:
        relation, story_id, best = Relation.EXACT, exact, 1.0
    else:
        lsh_candidates = session.execute(
            select(ItemSignature.signature, StoryItem.story_id, Item, ItemCard.keywords)
            .join(ItemLsh, ItemLsh.item_id == ItemSignature.item_id)
            .join(StoryItem, StoryItem.item_id == ItemSignature.item_id)
            .join(Item, Item.id == ItemSignature.item_id)
            .join(ItemCard, ItemCard.item_id == Item.id)
            .where(
                Item.first_seen_at >= since,
                or_(*[and_(ItemLsh.band == b, ItemLsh.hash == h) for b, h in enumerate(bands)]),
            )
            .distinct()
        ).tuples()
        candidates = list(lsh_candidates)
        if card.keywords:
            # same-event reports share entities but often only ~0.3-0.5 of their wording
            moment = _when(item)
            candidates += list(
                session.execute(
                    select(ItemSignature.signature, StoryItem.story_id, Item, ItemCard.keywords)
                    .join(StoryItem, StoryItem.item_id == ItemSignature.item_id)
                    .join(Item, Item.id == ItemSignature.item_id)
                    .join(ItemCard, ItemCard.item_id == Item.id)
                    .where(
                        Item.first_seen_at >= max(since, moment - EVENT_MAX_GAP),
                        ItemCard.keywords.has_any(array(card.keywords)),
                    )
                    .order_by(Item.first_seen_at.desc())
                    .limit(EVENT_CANDIDATES)
                ).tuples()
            )
        keywords = {word.lower() for word in card.keywords}
        for other_sig, other_story, other, other_keywords in candidates:
            score = similarity(sig, list(other_sig))
            if score >= thresholds.near and (
                best is None or relation is not Relation.NEAR or score > best
            ):
                relation, story_id, best = Relation.NEAR, other_story, score
            elif (
                relation is not Relation.NEAR
                and score >= thresholds.event
                and keywords & {word.lower() for word in other_keywords}
                and abs(_when(item) - _when(other)) <= EVENT_MAX_GAP
                and (best is None or score > best)
            ):
                relation, story_id, best = Relation.EVENT, other_story, score

    if (
        story_id is not None
        and relation is not Relation.EXACT
        and _one_source_full(session, story_id, source)
    ):
        relation, story_id, best = Relation.SEED, None, None
    session.add(ItemSignature(item_id=item.id, dedup_key=key, signature=sig, created_at=now))
    session.add_all(ItemLsh(item_id=item.id, band=b, hash=h) for b, h in enumerate(bands))
    if story_id is None:
        story = Story(
            representative_item_id=item.id,
            title_ko=card.title_ko,
            first_seen_at=item.first_seen_at,
            last_seen_at=item.first_seen_at,
            item_count=0,
            source_count=1,
            tracks=[],
            max_relevance=None,
        )
        session.add(story)
        session.flush()
    else:
        story = session.get(Story, story_id)  # type: ignore[assignment]
    session.add(
        StoryItem(
            item_id=item.id, story_id=story.id, relation=relation, similarity=best, joined_at=now
        )
    )
    session.flush()
    _attach(session, story, item, card, now)
    refs = extract_refs(item.url, item.title, item.summary)
    if refs:
        session.execute(
            insert(ItemRef)
            .values(
                [{"item_id": item.id, "kind": k, "value": v[:300], "meta": {}} for k, v in refs]
            )
            .on_conflict_do_nothing()
        )
    return relation, len(refs)


SINGLE_SOURCE_MAX = 20  # reports one publisher alone may add to a story by similarity
SAME_TITLE_MIN = (
    30  # characters: shorter headlines ("Weekly update") repeat without being one event
)


def _one_source_full(session: Session, story_id: int, source: Source) -> bool:
    """A story that already holds SINGLE_SOURCE_MAX reports, all from this publisher: a site's
    look-alike pages (release notes, notices, device pages), not one event (2026-10-05: one
    "ITRI 기술 혁신 브리프" story held 1,156 pages)."""
    story = session.get(Story, story_id)
    if story is None or story.source_count > 1 or story.item_count < SINGLE_SOURCE_MAX:
        return False
    domain = session.scalar(
        select(Source.official_domain)
        .join(Item, Item.source_id == Source.id)
        .where(Item.id == story.representative_item_id)
    )
    return domain == source.official_domain


def cluster(
    open_session: SessionScope,
    *,
    now: datetime,
    limit: int = 2000,
    thresholds: Thresholds | None = None,
) -> ClusterStats:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    stats = ClusterStats()
    with open_session() as session:
        for item, source, card in pending(session, limit=limit):
            relation, refs = assign(session, item, source, card, now=now, thresholds=thresholds)
            stats.processed += 1
            stats.refs += refs
            stats.by_relation[relation.value] = stats.by_relation.get(relation.value, 0) + 1
    return stats
