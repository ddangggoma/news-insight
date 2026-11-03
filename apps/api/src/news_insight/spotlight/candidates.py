"""The day's spotlight candidates per section, frozen at 04:40 KST (plan 18 §4).

The window is the briefing day's previous 04:40 KST up to its own 04:40 KST, counted by when an
item was first collected. Each section keeps its strongest 30 (products 40) by a section score;
the order of that list is the draft ranking (`stat_rank`) that the writer may adjust."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item, ItemDedup, ItemMetricSnapshot
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.spotlight.scoring import engagement, platform_stats, velocity, zscore
from news_insight.stories.models import Story, StoryItem

KST = ZoneInfo("Asia/Seoul")
SECTIONS: tuple[str, ...] = (
    "news",
    "product",
    "oss",
    "interview",
    "community",
    "research",
    "patent",
)
DEFAULT_LIMIT = 30
LIMITS = {"product": 40}
CID_PREFIX = {
    "news": "n",
    "product": "p",
    "oss": "o",
    "interview": "i",
    "community": "c",
    "research": "r",
    "patent": "t",
}
MIN_NEWS_SOURCES = 2
MIN_COMMUNITY_Z = 1.0


@dataclass
class Candidate:
    cid: str  # short id the writer answers with: n1, p3, ...
    section: str
    key: str  # story:{id} for an event, item:{id} for a single item
    item_ids: list[int]
    title_ko: str
    summary_ko: str
    url: str
    metrics: dict[str, Any]
    score: float
    stat_rank: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Row:
    """One collected item with what the sections need to know about it."""

    item: Item
    operator: str
    story_id: int | None
    url_key: str | None
    link_key: str | None


@dataclass(frozen=True)
class Fold:
    """Rows that report one event; a row without a story folds only with itself."""

    story_id: int | None
    rows: list[Row]


def window(day: date) -> tuple[datetime, datetime]:
    """Briefing date D covers D-1 04:40 … D 04:40 KST."""
    end = datetime.combine(day, time(4, 40), tzinfo=KST)
    return (end - timedelta(days=1)).astimezone(UTC), end.astimezone(UTC)


def _rows(
    session: Session, start: datetime, end: datetime, *where: ColumnElement[bool]
) -> list[Row]:
    stmt = (
        select(Item, Source.operator, StoryItem.story_id, ItemDedup.url_key, ItemDedup.link_key)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
        .where(
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
            Item.canary.is_(False),
            *where,
        )
        .order_by(Item.id)
    )
    return [Row(*row) for row in session.execute(stmt).tuples()]


def _eligible_items(session: Session, start: datetime, end: datetime) -> list[Row]:
    """Items first collected in the window that are neither canaries nor repeats of an earlier
    item."""
    return _rows(session, start, end, ItemDedup.duplicate_of.is_(None))


def _fold_stories(rows: Sequence[Row]) -> list[Fold]:
    """One fold per story (in order of first appearance); storyless rows stand alone."""
    folds: dict[int, Fold] = {}
    out: list[Fold] = []
    for row in rows:
        if row.story_id is None:
            out.append(Fold(None, [row]))
        elif row.story_id in folds:
            folds[row.story_id].rows.append(row)
        else:
            folds[row.story_id] = fold = Fold(row.story_id, [row])
            out.append(fold)
    return out


class Scorer:
    """Platform-normalised z of items, from each one's newest metrics snapshot by `at`."""

    def __init__(self, session: Session, *, at: datetime) -> None:
        self._session = session
        self._at = at
        self._per_platform, self._pooled = platform_stats(session, at=at)
        self.metrics: dict[int, dict[str, Any]] = {}
        self.z: dict[int, float] = {}

    def add(self, rows: Sequence[Row]) -> None:
        """Score rows not scored yet; items without a usable engagement get no z."""
        fresh = [row for row in rows if row.item.id not in self.metrics]
        if not fresh:
            return
        snapshots = self._session.scalars(
            select(ItemMetricSnapshot)
            .where(
                ItemMetricSnapshot.item_id.in_([row.item.id for row in fresh]),
                ItemMetricSnapshot.captured_at <= self._at,
            )
            .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at.desc())
            .distinct(ItemMetricSnapshot.item_id)
        )
        latest = {snap.item_id: dict(snap.metrics) for snap in snapshots}
        for row in fresh:
            item = row.item
            self.metrics[item.id] = latest.get(item.id, {})
            value = engagement(row.operator, self.metrics[item.id])
            if value is None:
                continue
            v = velocity(value, item.published_at, item.first_seen_at, self._at)
            self.z[item.id] = zscore(v, self._per_platform.get(row.operator), self._pooled)


def _cards(session: Session, item_ids: Sequence[int]) -> dict[int, ItemCard]:
    if not item_ids:
        return {}
    return {
        card.item_id: card
        for card in session.scalars(
            select(ItemCard).where(
                ItemCard.item_id.in_(item_ids), ItemCard.status == CardStatus.READY
            )
        )
    }


def _summary(card: ItemCard | None) -> str:
    return " ".join(card.summary_ko) if card is not None and card.summary_ko else ""


def _finish(section: str, drafts: list[Candidate]) -> list[Candidate]:
    """Order drafts by score (ties keep their arrival order), cut to the section limit and
    number them."""
    ranked = sorted(drafts, key=lambda c: -c.score)[: LIMITS.get(section, DEFAULT_LIMIT)]
    for rank, candidate in enumerate(ranked, start=1):
        candidate.stat_rank = rank
        candidate.cid = f"{CID_PREFIX[section]}{rank}"
    return ranked


def _news(
    session: Session,
    start: datetime,
    end: datetime,
    eligible: list[Row],
    scorer: Scorer,
) -> list[Candidate]:
    """Events reported by at least two sources, ranked by how many sources, then by how much the
    community talked about them (posts in the event, or posts sharing one of its articles)."""
    folds = [
        fold
        for fold in _fold_stories([r for r in eligible if r.item.track is Track.NEWS])
        if fold.story_id is not None
    ]
    story_ids = [fold.story_id for fold in folds if fold.story_id is not None]
    if not story_ids:
        return []
    stories = {s.id: s for s in session.scalars(select(Story).where(Story.id.in_(story_ids)))}

    # an article's url_key, wherever any member of the event was collected
    story_keys: dict[int, set[str]] = defaultdict(set)
    for story_id, url_key in session.execute(
        select(StoryItem.story_id, ItemDedup.url_key)
        .join(ItemDedup, ItemDedup.item_id == StoryItem.item_id)
        .where(StoryItem.story_id.in_(story_ids))
    ):
        story_keys[story_id].add(url_key)
    # A post sharing an article is stored as a repeat of it, so link repeats are read apart
    # from the eligible rows.
    all_keys = set().union(*story_keys.values()) if story_keys else set()
    sharing = (
        _rows(
            session,
            start,
            end,
            Item.track == Track.COMMUNITY,
            ItemDedup.link_key.in_(all_keys),
        )
        if all_keys
        else []
    )
    scorer.add(sharing)
    shared_by: dict[str, set[int]] = defaultdict(set)
    for row in sharing:
        if row.link_key is not None:
            shared_by[row.link_key].add(row.item.id)
    posts_in: dict[int, set[int]] = defaultdict(set)
    for row in eligible:
        if row.item.track is Track.COMMUNITY and row.story_id is not None:
            posts_in[row.story_id].add(row.item.id)

    cards = _cards(
        session,
        [story.representative_item_id for story in stories.values()]
        + [fold.rows[0].item.id for fold in folds],
    )
    drafts: list[Candidate] = []
    for fold in folds:
        assert fold.story_id is not None
        story = stories.get(fold.story_id)
        if story is None or story.source_count < MIN_NEWS_SOURCES:
            continue
        by_id = {row.item.id: row for row in fold.rows}
        rep = by_id.get(story.representative_item_id) or fold.rows[0]
        mentions = set(posts_in[fold.story_id])
        for url_key in story_keys[fold.story_id]:
            mentions |= shared_by[url_key]
        z_values = [scorer.z[i] for i in mentions if i in scorer.z]
        card = cards.get(rep.item.id)
        ids = [rep.item.id, *(r.item.id for r in fold.rows if r.item.id != rep.item.id)]
        drafts.append(
            Candidate(
                cid="",
                section="news",
                key=f"story:{story.id}",
                item_ids=ids,
                title_ko=(card.title_ko if card is not None else None)
                or story.title_ko
                or rep.item.title,
                summary_ko=_summary(card),
                url=rep.item.url,
                metrics={
                    "source_count": story.source_count,
                    "community_mentions": len(mentions),
                },
                score=float(
                    story.source_count * 100 + len(mentions) * 10 + max(z_values, default=0.0)
                ),
                stat_rank=0,
            )
        )
    return _finish("news", drafts)


def _community(session: Session, eligible: list[Row], scorer: Scorer) -> list[Candidate]:
    """Community posts clearly above their own platform's norm; posts of one event give way to
    its strongest."""
    scored = [
        row for row in eligible if row.item.track is Track.COMMUNITY and row.item.id in scorer.z
    ]
    best: list[Row] = []
    for fold in _fold_stories(scored):
        top = max(fold.rows, key=lambda r: scorer.z[r.item.id])
        if scorer.z[top.item.id] >= MIN_COMMUNITY_Z:
            best.append(top)
    cards = _cards(session, [row.item.id for row in best])
    drafts = []
    for row in best:
        card = cards.get(row.item.id)
        drafts.append(
            Candidate(
                cid="",
                section="community",
                key=f"item:{row.item.id}",
                item_ids=[row.item.id],
                title_ko=(card.title_ko if card is not None else None) or row.item.title,
                summary_ko=_summary(card),
                url=row.item.url,
                metrics={**scorer.metrics[row.item.id], "platform": row.operator},
                score=scorer.z[row.item.id],
                stat_rank=0,
            )
        )
    return _finish("community", drafts)


def collect_candidates(session: Session, *, day: date, now: datetime) -> dict[str, list[Candidate]]:
    """Every section's candidates for the briefing `day`. Metrics are read as of the window end
    (the freeze time), which is also when velocity is measured; `now` is when the freeze runs."""
    start, end = window(day)
    eligible = _eligible_items(session, start, end)
    scorer = Scorer(session, at=end)
    scorer.add(eligible)
    result: dict[str, list[Candidate]] = {section: [] for section in SECTIONS}
    result["news"] = _news(session, start, end, eligible, scorer)
    result["community"] = _community(session, eligible, scorer)
    return result
