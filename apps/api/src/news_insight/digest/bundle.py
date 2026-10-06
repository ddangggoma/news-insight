"""The digest input: previous KST day's first-seen items, grouped track → category → top items."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import ItemCard
from news_insight.companies.service import info_for
from news_insight.console.queries import latest_metrics
from news_insight.content.models import Item
from news_insight.content.normalize import truncate
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem

KST = ZoneInfo("Asia/Seoul")
SUMMARY_LIMIT = 280
OFF_TOPIC = frozenset({"irrelevant", "excluded"})
Row = tuple[Item, Source, ItemCard | None, Story | None]


@dataclass(frozen=True)
class Bundle:
    payload: dict[str, Any]
    item_ids: set[int]
    item_count: int


def digest_window(digest_date: date) -> tuple[datetime, datetime]:
    """Publication date D covers D-1 00:00 … D 00:00 KST."""
    end = datetime.combine(digest_date, time(0, 0), tzinfo=KST)
    return (end - timedelta(days=1)).astimezone(UTC), end.astimezone(UTC)


def build_bundle(
    session: Session,
    *,
    start: datetime,
    end: datetime,
    per_category: int = 12,
    item_ids: set[int] | None = None,
) -> Bundle:
    """Previous-day items, minus what P4 marked off-topic, one item per story.

    Items classified `irrelevant` or `excluded` (semiconductor asset investment) are left out;
    a story contributes only its representative, carrying how many sources covered it.
    """
    rows = list(
        session.execute(
            select(Item, Source, ItemCard, Story)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, ItemCard.item_id == Item.id)
            .outerjoin(StoryItem, StoryItem.item_id == Item.id)
            .outerjoin(Story, Story.id == StoryItem.story_id)
            .where(
                Item.first_seen_at >= start,
                Item.first_seen_at < end,
                *([Item.id.in_(item_ids)] if item_ids is not None else []),
            )
        ).tuples()
    )
    kept = [
        (item, source, card, story)
        for item, source, card, story in rows
        if not (card is not None and card.scope in OFF_TOPIC)
        and (story is None or story.representative_item_id == item.id)
    ]
    metrics = latest_metrics(session, [item.id for item, *_ in kept])
    registry = info_for(
        session, {key for _, _, card, _ in kept if card is not None for key in card.company_keys}
    )
    grouped: dict[Track, dict[str, list[Row]]] = {}
    for row in kept:
        grouped.setdefault(row[0].track, {}).setdefault(row[1].category, []).append(row)

    def rank(row: Row) -> tuple[int, int, int, float]:
        item, _, card, story = row
        coverage = story.source_count if story is not None else 1
        relevance = card.relevance if card is not None and card.relevance is not None else 50
        score = max(metrics.get(item.id, {}).values(), default=0)
        published = (item.published_at or item.first_seen_at).timestamp()
        return (coverage, relevance, score, published)

    tracks: list[dict[str, Any]] = []
    chosen: set[int] = set()
    for track in Track:
        categories = grouped.get(track)
        if not categories:
            continue
        sections = []
        for category, members in sorted(categories.items()):
            top = sorted(members, key=rank, reverse=True)[:per_category]
            chosen.update(row[0].id for row in top)
            sections.append(
                {
                    "category": category,
                    "items": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "title_ko": card.title_ko if card is not None else None,
                            "source": source.name,
                            "region": source.region.value,
                            "published_at": (item.published_at or item.first_seen_at).isoformat(),
                            "summary": truncate(item.summary, SUMMARY_LIMIT)
                            if item.summary
                            else None,
                            "metrics": metrics.get(item.id, {}),
                            "themes": list(card.themes) if card is not None else [],
                            "signal_type": card.signal_type if card is not None else None,
                            "covered_by_sources": story.source_count if story is not None else 1,
                            "companies": [
                                registry[key].name
                                for key in (card.company_keys if card is not None else [])
                                if key in registry
                            ],
                        }
                        for item, source, card, story in top
                    ],
                }
            )
        tracks.append(
            {
                "track": track.value,
                "item_count": sum(len(members) for members in categories.values()),
                "categories": sections,
            }
        )
    payload = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tracks": tracks,
    }
    return Bundle(payload=payload, item_ids=chosen, item_count=len(kept))
