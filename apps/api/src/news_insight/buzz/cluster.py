"""Buzz clusters (화제 묶음) of community posts, their threshold, and breaking (속보): design
§4 and §6 (docs/superpowers/specs/2026-11-19-community-signal-layer-design.md).

Every run re-reads the window's keys (no hashing: buzz/keys.py stored them) and joins posts that
share an article, a reference, or a near-identical title. A component keeps the id of the
cluster most of its posts already belong to, so a cluster's state (crossed, breaking, pushed,
summarised) survives the runs; two clusters that come together are merged into the larger.
"""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.buzz.keys import WINDOW, clean_title
from news_insight.buzz.models import BuzzCluster, BuzzClusterItem, BuzzItemKeys
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item, ItemDedup
from news_insight.sources.enums import Track
from news_insight.spotlight.scoring import PlatformStats, engagement, velocity, zscore
from news_insight.stories.minhash import NUM_PERM, similarity
from news_insight.stories.models import ItemRef

# ── thresholds (design §4.6, from the 2026-11-19 live day; revisit after a few days live)
MIN_AUTHORS = 3
MIN_PLATFORMS = 2
MIN_HEAT = 1.5
SOLO_AUTHORS = 5  # one platform alone (an HN or Threads pile-on) needs more people …
SOLO_HEAT = 3.0  # … and more heat
TITLE_SIMILARITY = 0.6  # MinHash, post to post: stricter than stories' 0.45, posts are noisy
BUCKET_CAP = 60  # posts compared within one LSH bucket (templates make huge ones)
# ── noise (design §4.4): 11 Mastodon accounts wrote 35 % of the day's toots (2026-11-19)
BOT_POSTS = 20  # posts in the window that make an author a feed or a bot
BOT_NAME = re.compile(r"(?:^|[^a-z0-9])bots?(?:[^a-z0-9]|$)|(?:news|feed|rss|alert)bot$")
BRIDGES = ("brid.gy", "rss-parrot", "rss.app", "rssfeed", "newsfeed")
# ── news (design §4.7) and breaking (§6)
NEWS_LOOKBACK = timedelta(hours=48)
NEWS_TITLE_SIMILARITY = 0.5  # pg_trgm
NEWS_KEEP = 10
BREAKING_FRESH = timedelta(hours=6)
NORM_DAYS = 2


@dataclass
class Post:
    item_id: int
    platform: str
    author: str | None
    links: list[str]
    refs: list[str]
    signature: list[int]
    bands: list[int]
    first_seen_at: datetime
    bot: bool = False

    @property
    def person(self) -> str:
        """Who counts: the author, or the post itself where a platform names none (front pages,
        hot lists)."""
        return self.author or f"{self.platform}:#{self.item_id}"


@dataclass
class ClusterStats:
    posts: int = 0
    computed: int = 0
    clusters: int = 0
    merged: int = 0
    crossed: int = 0
    breaking: int = 0
    linked: int = 0
    notes: list[str] = field(default_factory=list)


def load_posts(session: Session, *, now: datetime) -> list[Post]:
    rows = session.execute(
        select(
            BuzzItemKeys.item_id,
            BuzzItemKeys.platform,
            BuzzItemKeys.author,
            BuzzItemKeys.links,
            BuzzItemKeys.refs,
            BuzzItemKeys.signature,
            BuzzItemKeys.bands,
            BuzzItemKeys.first_seen_at,
        )
        .where(BuzzItemKeys.first_seen_at >= now - WINDOW)
        .order_by(BuzzItemKeys.first_seen_at, BuzzItemKeys.item_id)
    ).tuples()
    return [
        Post(
            item_id=item_id,
            platform=platform,
            author=author,
            links=list(links or []),
            refs=list(refs or []),
            signature=list(sig or []),
            bands=list(bands or []),
            first_seen_at=first_seen,
        )
        for item_id, platform, author, links, refs, sig, bands, first_seen in rows
    ]


def bot_like(author: str) -> bool:
    name = author.split(":", 1)[-1]
    local, _, domain = name.partition("@")
    return bool(BOT_NAME.search(local)) or any(mark in domain or mark in local for mark in BRIDGES)


def mark_bots(posts: Sequence[Post]) -> set[str]:
    """Feed and bot accounts: many posts in the window, a bot's name, or a bridge account."""
    counts = Counter(post.author for post in posts if post.author)
    bots = {author for author, n in counts.items() if n >= BOT_POSTS or bot_like(author)}
    for post in posts:
        post.bot = post.author in bots
    return bots


def components(posts: Sequence[Post]) -> list[list[int]]:
    """Indexes of posts joined by a shared link or reference, or by a near-identical title
    (bots' titles never join: their templates look alike), as lists of two or more."""
    parent = list(range(len(posts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    first: dict[str, int] = {}
    for index, post in enumerate(posts):
        for key in (*(f"l:{k}" for k in post.links), *(f"r:{r}" for r in post.refs)):
            union(index, first.setdefault(key, index))
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, post in enumerate(posts):
        if post.bot or len(post.signature) != NUM_PERM:
            continue
        for band, value in enumerate(post.bands):
            bucket = buckets[(band, value)]
            if len(bucket) < BUCKET_CAP:
                bucket.append(index)
    checked: set[tuple[int, int]] = set()
    for bucket in buckets.values():
        for n, a in enumerate(bucket):
            for b in bucket[n + 1 :]:
                if (a, b) in checked or find(a) == find(b):
                    continue
                checked.add((a, b))
                if similarity(posts[a].signature, posts[b].signature) >= TITLE_SIMILARITY:
                    union(a, b)
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(posts)):
        groups[find(index)].append(index)
    return [members for members in groups.values() if len(members) >= 2]


def _merge(session: Session, source: BuzzCluster, target: BuzzCluster) -> None:
    """Fold `source` into `target`: its posts move, and what already happened to it (crossed,
    breaking, pushed, summarised) is kept, so a merge never pushes the same story twice."""
    session.execute(
        update(BuzzClusterItem)
        .where(BuzzClusterItem.cluster_id == source.id)
        .values(cluster_id=target.id)
    )
    target.first_seen_at = min(target.first_seen_at, source.first_seen_at)
    target.last_seen_at = max(target.last_seen_at, source.last_seen_at)
    for name in ("crossed_at", "breaking_at"):
        values = [v for v in (getattr(target, name), getattr(source, name)) if v is not None]
        setattr(target, name, min(values) if values else None)
    target.breaking = target.breaking or source.breaking
    if target.pushed_at is None and source.pushed_at is not None:
        target.pushed_at, target.push_channels = source.pushed_at, list(source.push_channels)
    if target.summarized_at is None and source.summarized_at is not None:
        for name in (
            "title_ko",
            "summary_ko",
            "keywords",
            "is_event",
            "relevant",
            "summary_engine",
            "summary_model",
            "summarized_at",
            "summary_posts",
            "summary_count",
        ):
            setattr(target, name, getattr(source, name))
    source.merged_into = target.id


def persist(
    session: Session, posts: Sequence[Post], groups: Sequence[Sequence[int]], *, now: datetime
) -> tuple[dict[int, list[Post]], int]:
    """Clusters for the components (by majority of their posts' clusters; new ones otherwise),
    and the window's posts per cluster. Membership is sticky: a post stays in its cluster when
    the post that joined it leaves the window."""
    ids = [post.item_id for post in posts]
    current: dict[int, int] = {}
    if ids:
        for item_id, cluster_id in session.execute(
            select(BuzzClusterItem.item_id, BuzzClusterItem.cluster_id).where(
                BuzzClusterItem.item_id.in_(ids)
            )
        ).tuples():
            current[item_id] = cluster_id
    merged = 0
    for group in groups:
        members = [posts[i] for i in group]
        counts = Counter(current[p.item_id] for p in members if p.item_id in current)
        if counts:
            target_id = min(counts, key=lambda c: (-counts[c], c))
            target = session.get(BuzzCluster, target_id)
            assert target is not None
            for other_id in sorted(counts):
                if other_id == target_id:
                    continue
                other = session.get(BuzzCluster, other_id)
                if other is not None and other.merged_into is None:
                    _merge(session, other, target)
                    merged += 1
                for item_id, cluster_id in list(current.items()):
                    if cluster_id == other_id:
                        current[item_id] = target_id
        else:
            target = BuzzCluster(
                first_seen_at=min(p.first_seen_at for p in members),
                last_seen_at=max(p.first_seen_at for p in members),
                updated_at=now,
                platforms=[],
                news_item_ids=[],
                summary_ko=[],
                keywords=[],
                push_channels=[],
            )
            session.add(target)
            session.flush()
        moving = [p.item_id for p in members if current.get(p.item_id) != target.id]
        if moving:
            statement = insert(BuzzClusterItem).values(
                [{"item_id": i, "cluster_id": target.id, "joined_at": now} for i in moving]
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[BuzzClusterItem.item_id],
                    set_={"cluster_id": target.id, "joined_at": now},
                )
            )
            for item_id in moving:
                current[item_id] = target.id
    session.flush()
    by_cluster: dict[int, list[Post]] = defaultdict(list)
    for post in posts:
        if post.item_id in current:
            by_cluster[current[post.item_id]].append(post)
    return dict(by_cluster), merged


_NORMS = text(
    """
    select s.operator, i.published_at, i.first_seen_at, m.metrics
    from items i
    join sources s on s.id = i.source_id
    join lateral (
      select x.metrics from item_metric_snapshots x
      where x.item_id = i.id and x.captured_at <= :at
      order by x.captured_at desc limit 1
    ) m on true
    where i.track = 'community' and i.first_seen_at >= :since and i.first_seen_at <= :at
    """
)
_LATEST = text(
    """
    select i.id, s.operator, i.published_at, i.first_seen_at, m.metrics
    from items i
    join sources s on s.id = i.source_id
    join lateral (
      select x.metrics from item_metric_snapshots x
      where x.item_id = i.id and x.captured_at <= :at
      order by x.captured_at desc limit 1
    ) m on true
    where i.id = any(:ids)
    """
)


def _stats(values: list[float]) -> PlatformStats:
    n = len(values)
    if not n:
        return PlatformStats(0.0, 0.0, 0)
    mean = sum(values) / n
    return PlatformStats(mean, math.sqrt(sum((v - mean) ** 2 for v in values) / n), n)


class Heat:
    """Platform-normalised z of posts (spotlight/scoring.py), the norms from community posts of
    the last NORM_DAYS days at their newest snapshot."""

    def __init__(self, session: Session, *, at: datetime) -> None:
        by_operator: dict[str, list[float]] = defaultdict(list)
        pooled: list[float] = []
        for operator, published, first_seen, metrics in session.execute(
            _NORMS, {"at": at, "since": at - timedelta(days=NORM_DAYS)}
        ).tuples():
            value = engagement(operator, metrics or {})
            if value is not None:
                v = velocity(value, published, first_seen, at)
                by_operator[operator].append(v)
                pooled.append(v)
        self._session, self._at = session, at
        self._norms = {op: _stats(values) for op, values in by_operator.items()}
        self._pooled = _stats(pooled)

    def z(self, item_ids: Iterable[int]) -> dict[int, float]:
        ids = list(item_ids)
        if not ids:
            return {}
        out: dict[int, float] = {}
        for item_id, operator, published, first_seen, metrics in self._session.execute(
            _LATEST, {"at": self._at, "ids": ids}
        ).tuples():
            value = engagement(operator, metrics or {})
            if value is not None:
                v = velocity(value, published, first_seen, self._at)
                out[item_id] = zscore(v, self._norms.get(operator), self._pooled)
        return out


class Scores(Protocol):
    def z(self, item_ids: Iterable[int]) -> dict[int, float]: ...


def over_threshold(authors: int, platforms: int, heat: float) -> bool:
    return (authors >= MIN_AUTHORS and platforms >= MIN_PLATFORMS and heat >= MIN_HEAT) or (
        authors >= SOLO_AUTHORS and heat >= SOLO_HEAT
    )


def score_of(authors: int, platforms: int, heat: float) -> float:
    return round(10 * platforms + 4 * min(authors, 20) + 5 * heat, 2)


def _news_ids(
    session: Session, cluster: BuzzCluster, posts: Sequence[Post]
) -> list[tuple[int, datetime]]:
    """News items that tell the cluster's story: an article the posts share, a reference they
    carry, or a close headline (the lead post's, or the Korean summary title against cards)."""
    since = cluster.first_seen_at - NEWS_LOOKBACK
    found: dict[int, datetime] = {}

    def keep(rows: Iterable[tuple[int, datetime]]) -> None:
        for item_id, first_seen in rows:
            found[item_id] = first_seen

    news = (Item.track == Track.NEWS, Item.first_seen_at >= since, Item.canary.is_(False))
    links = sorted({key for post in posts for key in post.links})
    if links:
        keep(
            session.execute(
                select(Item.id, Item.first_seen_at)
                .join(ItemDedup, ItemDedup.item_id == Item.id)
                .where(ItemDedup.url_key.in_(links), *news)
            ).tuples()
        )
    pairs = sorted({tuple(ref.split(":", 1)) for post in posts for ref in post.refs if ":" in ref})
    if pairs:
        keep(
            session.execute(
                select(Item.id, Item.first_seen_at)
                .join(ItemRef, ItemRef.item_id == Item.id)
                .where(tuple_(ItemRef.kind, ItemRef.value).in_(pairs), *news)
            ).tuples()
        )
    lead = session.get(Item, cluster.lead_item_id) if cluster.lead_item_id else None
    headline = clean_title(lead.title) if lead is not None else ""
    if len(headline.split()) >= 4:
        keep(
            session.execute(
                select(Item.id, Item.first_seen_at)
                .where(
                    Item.title.op("%")(headline),
                    func.similarity(Item.title, headline) >= NEWS_TITLE_SIMILARITY,
                    *news,
                )
                .order_by(func.similarity(Item.title, headline).desc())
                .limit(NEWS_KEEP)
            ).tuples()
        )
    if cluster.title_ko:
        keep(
            session.execute(
                select(Item.id, Item.first_seen_at)
                .join(ItemCard, ItemCard.item_id == Item.id)
                .where(
                    ItemCard.status == CardStatus.READY,
                    ItemCard.title_ko.op("%")(cluster.title_ko),
                    func.similarity(ItemCard.title_ko, cluster.title_ko) >= NEWS_TITLE_SIMILARITY,
                    *news,
                )
                .order_by(func.similarity(ItemCard.title_ko, cluster.title_ko).desc())
                .limit(NEWS_KEEP)
            ).tuples()
        )
    return sorted(found.items(), key=lambda pair: (pair[1], pair[0]))


def measure(
    session: Session,
    by_cluster: dict[int, list[Post]],
    *,
    now: datetime,
    heat: Scores | None = None,
) -> ClusterStats:
    """Counts, heat and score of each cluster with posts in the window; the threshold, the news
    that told the story, and breaking at the moment a cluster first crosses."""
    stats = ClusterStats(clusters=len(by_cluster))
    clusters = {
        c.id: c
        for c in session.scalars(select(BuzzCluster).where(BuzzCluster.id.in_(list(by_cluster))))
    }
    people: dict[int, list[Post]] = {
        cid: [p for p in posts if not p.bot] for cid, posts in by_cluster.items()
    }
    hopeful = [
        cid
        for cid, humans in people.items()
        if len({p.person for p in humans}) >= MIN_AUTHORS
        or (clusters.get(cid) is not None and clusters[cid].crossed_at is not None)
    ]
    z: dict[int, float] = {}
    if hopeful:
        heat = heat or Heat(session, at=now)
        z = heat.z(p.item_id for cid in hopeful for p in people[cid])
    for cid, posts in by_cluster.items():
        cluster = clusters.get(cid)
        if cluster is None or cluster.merged_into is not None:
            continue
        humans = people[cid]
        authors = len({p.person for p in humans})
        platforms = sorted({p.platform for p in humans})
        warmth = round(sum(max(z.get(p.item_id, 0.0), 0.0) for p in humans), 2)
        lead = max(
            humans or posts,
            key=lambda p: (z.get(p.item_id, float("-inf")), -p.first_seen_at.timestamp()),
        )
        cluster.first_seen_at = min(cluster.first_seen_at, *(p.first_seen_at for p in posts))
        cluster.last_seen_at = max(cluster.last_seen_at, *(p.first_seen_at for p in posts))
        cluster.post_count, cluster.human_posts = len(posts), len(humans)
        cluster.author_count, cluster.platforms = authors, platforms
        cluster.platform_count = len(platforms)
        cluster.heat, cluster.score = warmth, score_of(authors, len(platforms), warmth)
        cluster.lead_item_id = lead.item_id
        cluster.updated_at = now
        crossing = cluster.crossed_at is None and over_threshold(authors, len(platforms), warmth)
        if crossing:
            cluster.crossed_at = now
            stats.crossed += 1
        if cluster.crossed_at is None:
            continue
        news = _news_ids(session, cluster, posts)
        if news:
            stats.linked += 1
            cluster.news_item_ids = [item_id for item_id, _ in news[:NEWS_KEEP]]
            cluster.news_first_seen_at = news[0][1]
        if crossing and not news and cluster.first_seen_at >= now - BREAKING_FRESH:
            cluster.breaking, cluster.breaking_at = True, now
            stats.breaking += 1
        if cluster.breaking and cluster.news_first_seen_at is not None:
            if cluster.news_first_seen_at <= cluster.first_seen_at and cluster.pushed_at is None:
                # the news was there before the first post: found late (a Korean title match
                # after the summary), it was never community-first
                cluster.breaking, cluster.breaking_at = False, None
            elif cluster.news_caught_up_at is None:
                cluster.news_caught_up_at = cluster.news_first_seen_at
    session.flush()
    return stats


def run(session: Session, *, now: datetime, heat: Scores | None = None) -> ClusterStats:
    """One pass: keys for new posts, clusters, threshold, news, breaking (not the push)."""
    from news_insight.buzz.keys import compute_pending

    computed = compute_pending(session, now=now)
    posts = load_posts(session, now=now)
    mark_bots(posts)
    groups = components(posts)
    by_cluster, merged = persist(session, posts, groups, now=now)
    stats = measure(session, by_cluster, now=now, heat=heat)
    stats.posts, stats.computed, stats.merged = len(posts), computed, merged
    return stats
