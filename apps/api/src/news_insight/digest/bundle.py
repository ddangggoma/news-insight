"""The digest input: previous KST day's first-seen items, grouped track → category → top items."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.console.queries import latest_metrics
from news_insight.content.models import Item
from news_insight.content.normalize import truncate
from news_insight.sources.enums import Track
from news_insight.sources.models import Source

KST = ZoneInfo("Asia/Seoul")
SUMMARY_LIMIT = 280


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
    session: Session, *, start: datetime, end: datetime, per_category: int = 12
) -> Bundle:
    pairs = list(
        session.execute(
            select(Item, Source)
            .join(Source, Source.id == Item.source_id)
            .where(Item.first_seen_at >= start, Item.first_seen_at < end)
        ).tuples()
    )
    metrics = latest_metrics(session, [item.id for item, _ in pairs])
    grouped: dict[Track, dict[str, list[tuple[Item, Source]]]] = {}
    for item, source in pairs:
        grouped.setdefault(item.track, {}).setdefault(source.category, []).append((item, source))

    def rank(pair: tuple[Item, Source]) -> tuple[int, float]:
        item, _ = pair
        score = max(metrics.get(item.id, {}).values(), default=0)
        published = (item.published_at or item.first_seen_at).timestamp()
        return (score, published)

    tracks: list[dict[str, Any]] = []
    chosen: set[int] = set()
    for track in Track:
        categories = grouped.get(track)
        if not categories:
            continue
        sections = []
        for category, members in sorted(categories.items()):
            top = sorted(members, key=rank, reverse=True)[:per_category]
            chosen.update(item.id for item, _ in top)
            sections.append(
                {
                    "category": category,
                    "items": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "source": source.name,
                            "region": source.region.value,
                            "published_at": (item.published_at or item.first_seen_at).isoformat(),
                            "summary": truncate(item.summary, SUMMARY_LIMIT)
                            if item.summary
                            else None,
                            "metrics": metrics.get(item.id, {}),
                        }
                        for item, source in top
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
    return Bundle(payload=payload, item_ids=chosen, item_count=len(pairs))
