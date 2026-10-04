"""Out-of-taxonomy topic candidates for the monthly taxonomy review (checklist CLS-1)."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import Text, func, literal_column, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.console.queries import item_rows
from news_insight.console.schemas import TopicCandidate
from news_insight.content.models import Item
from news_insight.sources.models import Source

RECENT = timedelta(days=7)
EXAMPLES = 3


def candidate_key(phrase: str) -> str:
    return re.sub(r"[\s\-_·]", "", phrase.lower())


@dataclass
class _Bucket:
    labels: Counter[str] = field(default_factory=Counter)
    items: dict[int, tuple[datetime, int]] = field(default_factory=dict)
    fields: Counter[str] = field(default_factory=Counter)


def topic_candidates(
    session: Session, *, days: int, now: datetime, min_count: int = 2, limit: int = 50
) -> list[TopicCandidate]:
    since = now - timedelta(days=days)
    phrase = literal_column("tc.value", Text)
    element = func.jsonb_array_elements_text(ItemCard.topic_candidates).table_valued("value")
    rows = session.execute(
        select(phrase, Item.id, Item.first_seen_at, ItemCard.field, ItemCard.relevance)
        .select_from(ItemCard)
        .join(Item, Item.id == ItemCard.item_id)
        .join(element.alias("tc"), literal_column("true"))
        .where(
            ItemCard.status == CardStatus.READY,
            ItemCard.scope.in_(["dx", "dx_dependency"]),
            Item.first_seen_at >= since,
        )
    ).tuples()
    buckets: dict[str, _Bucket] = defaultdict(_Bucket)
    for text, item_id, seen, card_field, relevance in rows:
        bucket = buckets[candidate_key(text)]
        bucket.labels[text] += 1
        bucket.items[item_id] = (seen, relevance or 0)
        if card_field:
            bucket.fields[card_field] += 1
    ranked = sorted(
        (b for b in buckets.items() if len(b[1].items) >= min_count),
        key=lambda kv: (-len(kv[1].items), kv[0]),
    )[:limit]
    example_ids = {
        item_id
        for _, bucket in ranked
        for item_id, _ in sorted(bucket.items.items(), key=lambda kv: -kv[1][1])[:EXAMPLES]
    }
    pairs = session.execute(
        select(Item, Source)
        .join(Source, Source.id == Item.source_id)
        .where(Item.id.in_(example_ids))
    ).tuples()
    rows_by_id = {row.id: row for row in item_rows(session, list(pairs))}
    result = []
    for key, bucket in ranked:
        dates = [at for at, _ in bucket.items.values()]
        top = sorted(bucket.items.items(), key=lambda kv: -kv[1][1])[:EXAMPLES]
        result.append(
            TopicCandidate(
                key=key,
                label=bucket.labels.most_common(1)[0][0],
                count=len(bucket.items),
                recent=sum(1 for at in dates if at >= now - RECENT),
                first_seen=min(dates),
                last_seen=max(dates),
                fields=dict(bucket.fields.most_common(3)),
                examples=[rows_by_id[i] for i, _ in top if i in rows_by_id],
            )
        )
    return result
