"""The reader's 화제·속보 list (design §9): clusters over the threshold, breaking first. Signals
only: posts are shown inside their cluster, never as feed items."""

from collections import defaultdict
from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.buzz.models import BuzzCluster, BuzzClusterItem, BuzzItemKeys
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.sources.models import Source

LIMIT = 40
POSTS = 5
NEWS = 3


class BuzzPost(BaseModel):
    id: int
    title: str
    url: str
    platform: str
    author: str | None
    first_seen_at: datetime


class BuzzNews(BaseModel):
    id: int
    title: str
    url: str
    source_name: str
    first_seen_at: datetime


class BuzzClusterOut(BaseModel):
    id: int
    title: str  # the Korean summary title, or the lead post's own words until it is written
    summary: list[str]
    keywords: list[str]
    summarized: bool
    breaking: bool
    breaking_at: datetime | None
    is_event: bool | None
    # minutes the community was ahead of the first news report (breaking clusters the news told)
    lead_minutes: int | None
    first_seen_at: datetime
    last_seen_at: datetime
    crossed_at: datetime
    authors: int
    posts: int
    platforms: list[str]
    heat: float
    score: float
    sample: list[BuzzPost]
    news: list[BuzzNews]


class BuzzView(BaseModel):
    generated_at: datetime
    hours: int
    clusters: list[BuzzClusterOut]


def buzz_view(session: Session, *, now: datetime, hours: int = 24) -> BuzzView:
    clusters = list(
        session.scalars(
            select(BuzzCluster)
            .where(
                BuzzCluster.crossed_at.is_not(None),
                BuzzCluster.merged_into.is_(None),
                BuzzCluster.last_seen_at >= now - timedelta(hours=hours),
            )
            .order_by(BuzzCluster.score.desc(), BuzzCluster.id)
            .limit(LIMIT)
        )
    )
    # breaking first (newest first), then by score; off-topic summaries go last
    clusters.sort(
        key=lambda c: (
            c.relevant is False,
            not c.breaking,
            -(c.breaking_at.timestamp() if c.breaking and c.breaking_at else 0),
            -c.score,
        )
    )
    ids = [c.id for c in clusters]
    samples: dict[int, list[BuzzPost]] = defaultdict(list)
    if ids:
        rows = session.execute(
            select(BuzzClusterItem.cluster_id, Item, BuzzItemKeys.platform)
            .join(Item, Item.id == BuzzClusterItem.item_id)
            .outerjoin(BuzzItemKeys, BuzzItemKeys.item_id == Item.id)
            .where(BuzzClusterItem.cluster_id.in_(ids))
            .order_by(Item.first_seen_at.desc(), Item.id.desc())
        ).tuples()
        leads = {c.id: c.lead_item_id for c in clusters}
        pool: dict[int, list[BuzzPost]] = defaultdict(list)
        for cluster_id, item, platform in rows:
            entry = BuzzPost(
                id=item.id,
                title=item.title,
                url=item.url,
                platform=platform or "",
                author=item.author,
                first_seen_at=item.first_seen_at,
            )
            if item.id == leads[cluster_id]:
                pool[cluster_id].insert(0, entry)  # the lead post first, then the newest
            else:
                pool[cluster_id].append(entry)
        for cluster_id, posts in pool.items():
            samples[cluster_id] = posts[:POSTS]
    news_ids = sorted({i for c in clusters for i in c.news_item_ids[:NEWS]})
    news: dict[int, BuzzNews] = {}
    if news_ids:
        for item, source, card in session.execute(
            select(Item, Source, ItemCard)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(
                ItemCard, (ItemCard.item_id == Item.id) & (ItemCard.status == CardStatus.READY)
            )
            .where(Item.id.in_(news_ids))
        ).tuples():
            news[item.id] = BuzzNews(
                id=item.id,
                title=(card.title_ko if card is not None else None) or item.title,
                url=item.url,
                source_name=source.name,
                first_seen_at=item.first_seen_at,
            )
    out = []
    for c in clusters:
        sample = samples.get(c.id, [])
        lead_minutes = None
        if c.breaking and c.news_first_seen_at is not None:
            lead_minutes = max(
                0, int((c.news_first_seen_at - c.first_seen_at).total_seconds() // 60)
            )
        assert c.crossed_at is not None
        out.append(
            BuzzClusterOut(
                id=c.id,
                title=c.title_ko or (sample[0].title if sample else ""),
                summary=list(c.summary_ko),
                keywords=list(c.keywords),
                summarized=c.summarized_at is not None,
                breaking=c.breaking,
                breaking_at=c.breaking_at,
                is_event=c.is_event,
                lead_minutes=lead_minutes,
                first_seen_at=c.first_seen_at,
                last_seen_at=c.last_seen_at,
                crossed_at=c.crossed_at,
                authors=c.author_count,
                posts=c.human_posts,
                platforms=list(c.platforms),
                heat=c.heat,
                score=c.score,
                sample=sample,
                news=[news[i] for i in c.news_item_ids[:NEWS] if i in news],
            )
        )
    return BuzzView(generated_at=now, hours=hours, clusters=out)
