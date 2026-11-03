"""The day's spotlight candidates per section, frozen at 04:40 KST (plan 18 §4).

The window is the briefing day's previous 04:40 KST up to its own 04:40 KST, counted by when an
item was first collected. Each section keeps its strongest 30 (products 40) by a section score;
the order of that list is the draft ranking (`stat_rank`) that the writer may adjust."""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session, load_only

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item, ItemDedup, ItemMetricSnapshot
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.spotlight.scoring import engagement, platform_stats, velocity, zscore
from news_insight.stories.models import ItemRef, Story, StoryItem

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
MIN_PRODUCT_SOURCES = 2
MIN_PRODUCT_Z = 1.0
MIN_OSS_Z = 1.0
MIN_OSS_MENTIONS = 2
OSS_MENTION_WEIGHT = 0.5
OSS_REF_KINDS = ("github", "hf")
RESEARCH_MENTION_WEIGHT = 10
RESEARCH_REF_KINDS = ("doi", "arxiv")
MIN_HF_UPVOTES = 10
HF_PAPERS = "Hugging Face Daily Papers"
YOUTUBE = "Google LLC (YouTube Data API)"
INTERVIEW_CATEGORIES = ("podcast_newsletter", "video_channel")
INTERVIEW_PATTERN = re.compile(
    r"\b(interview|keynote|podcast|fireside|says|Q&A)\b|인터뷰|대담|기조연설|CEO|CTO", re.I
)
PATENT_OFFICE = "patent_office"


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
    category: str


@dataclass(frozen=True)
class Fold:
    """Rows that report one event; a row without a story folds only with itself."""

    story_id: int | None
    rows: list[Row]


def window(day: date) -> tuple[datetime, datetime]:
    """Briefing date D covers D-1 04:40 … D 04:40 KST."""
    end = datetime.combine(day, time(4, 40), tzinfo=KST)
    return (end - timedelta(days=1)).astimezone(UTC), end.astimezone(UTC)


# Repeats of an earlier item stay out, except a post sharing a known article: that is stored as a
# repeat of the article (matched by its link) but is the community's own post (ruling R6).
ELIGIBLE = or_(ItemDedup.duplicate_of.is_(None), ItemDedup.matched_by == "link")
# The text-heavy columns (body, summary, …) are never needed here and there are ~20k rows a day.
_ITEM_COLUMNS = load_only(
    Item.id, Item.track, Item.title, Item.url, Item.published_at, Item.first_seen_at
)


def _rows(
    session: Session, start: datetime, end: datetime, *where: ColumnElement[bool]
) -> list[Row]:
    stmt = (
        select(
            Item,
            Source.operator,
            StoryItem.story_id,
            ItemDedup.url_key,
            ItemDedup.link_key,
            Source.category,
        )
        .options(_ITEM_COLUMNS)
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
    item (a post sharing a known article is kept)."""
    return _rows(session, start, end, ELIGIBLE)


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


def _stories(session: Session, folds: Sequence[Fold]) -> dict[int, Story]:
    ids = [fold.story_id for fold in folds if fold.story_id is not None]
    if not ids:
        return {}
    return {s.id: s for s in session.scalars(select(Story).where(Story.id.in_(ids)))}


def _lead(fold: Fold, story: Story | None) -> Row:
    """The row that speaks for a fold: the story's representative when it is a member."""
    if story is not None:
        for row in fold.rows:
            if row.item.id == story.representative_item_id:
                return row
    return fold.rows[0]


def _draft(
    section: str,
    fold: Fold,
    story: Story | None,
    lead: Row,
    card: ItemCard | None,
    *,
    metrics: dict[str, Any],
    score: float,
) -> Candidate:
    """An entry for an event (`story:{id}`) or a single item (`item:{id}`)."""
    return Candidate(
        cid="",
        section=section,
        key=f"story:{fold.story_id}" if fold.story_id is not None else f"item:{lead.item.id}",
        item_ids=[lead.item.id, *(r.item.id for r in fold.rows if r.item.id != lead.item.id)],
        title_ko=(card.title_ko if card is not None else None)
        or (story.title_ko if story is not None else None)
        or lead.item.title,
        summary_ko=_summary(card),
        url=lead.item.url,
        metrics=metrics,
        score=score,
        stat_rank=0,
    )


class Mentions:
    """Community talk about an event: posts that belong to its story, or that share one of its
    articles (found by the link a post carries). Posts are scored as they are first needed."""

    def __init__(
        self, session: Session, start: datetime, end: datetime, eligible: list[Row], scorer: Scorer
    ) -> None:
        self._session, self._start, self._end, self._scorer = session, start, end, scorer
        community = [row for row in eligible if row.item.track is Track.COMMUNITY]
        scorer.add(community)  # the community section ranks every one of them
        self._posts_in: dict[int, set[int]] = defaultdict(set)
        for row in community:
            if row.story_id is not None:
                self._posts_in[row.story_id].add(row.item.id)
        self._shared: dict[str, set[int]] = {}

    def of(self, folds: Sequence[Fold]) -> list[set[int]]:
        """Distinct mentioning posts per fold (never the fold's own items), in fold order."""
        story_ids = [fold.story_id for fold in folds if fold.story_id is not None]
        # an article's url_key, wherever any member of the event was collected
        story_keys: dict[int, set[str]] = defaultdict(set)
        if story_ids:
            for story_id, url_key in self._session.execute(
                select(StoryItem.story_id, ItemDedup.url_key)
                .join(ItemDedup, ItemDedup.item_id == StoryItem.item_id)
                .where(StoryItem.story_id.in_(story_ids))
            ):
                story_keys[story_id].add(url_key)
        keys: list[set[str]] = []
        for fold in folds:
            own = {row.url_key for row in fold.rows if row.url_key is not None}
            keys.append(own | story_keys[fold.story_id] if fold.story_id is not None else own)
        self._load_sharing(set().union(*keys) if keys else set())
        out: list[set[int]] = []
        for fold, fold_keys in zip(folds, keys, strict=True):
            ids = set(self._posts_in[fold.story_id]) if fold.story_id is not None else set()
            for key in fold_keys:
                ids |= self._shared[key]
            out.append(ids - {row.item.id for row in fold.rows})
        return out

    def _load_sharing(self, keys: set[str]) -> None:
        """A post sharing an article is stored as a repeat of it, so link repeats are read apart
        from the eligible rows."""
        fresh = keys - self._shared.keys()
        if not fresh:
            return
        for key in fresh:
            self._shared[key] = set()
        rows = _rows(
            self._session,
            self._start,
            self._end,
            Item.track == Track.COMMUNITY,
            ItemDedup.link_key.in_(fresh),
        )
        self._scorer.add(rows)
        for row in rows:
            if row.link_key is not None:
                self._shared[row.link_key].add(row.item.id)

    def z_sum(self, ids: set[int]) -> float:
        """Total standing of the posts above their platform's norm."""
        return sum(max(self._scorer.z.get(i, 0.0), 0.0) for i in ids)

    def best_z(self, ids: set[int]) -> float:
        return max((self._scorer.z[i] for i in ids if i in self._scorer.z), default=0.0)


def _signal_items(session: Session, start: datetime, end: datetime, signal: str) -> set[int]:
    """Items first collected in the window whose ready card is of this signal type."""
    return set(
        session.scalars(
            select(ItemCard.item_id)
            .join(Item, Item.id == ItemCard.item_id)
            .where(
                Item.first_seen_at >= start,
                Item.first_seen_at < end,
                ItemCard.status == CardStatus.READY,
                ItemCard.signal_type == signal,
            )
        )
    )


def _ref_mentions(
    session: Session,
    start: datetime,
    end: datetime,
    item_ids: Sequence[int],
    kinds: tuple[str, ...],
) -> dict[int, set[int]]:
    """Other items in the window, of any track, that carry one of the same references (`kinds`)
    as each given item. Repeats of an earlier item do not count, except a post sharing a known
    article."""
    if not item_ids:
        return {}
    own: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for item_id, kind, value in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value).where(
            ItemRef.item_id.in_(item_ids), ItemRef.kind.in_(kinds)
        )
    ):
        own[item_id].add((kind, value))
    values = {value for refs in own.values() for _, value in refs}
    if not values:
        return {}
    carriers: dict[tuple[str, str], set[int]] = defaultdict(set)
    for item_id, kind, value in session.execute(
        select(ItemRef.item_id, ItemRef.kind, ItemRef.value)
        .join(Item, Item.id == ItemRef.item_id)
        .outerjoin(ItemDedup, ItemDedup.item_id == Item.id)
        .where(
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
            Item.canary.is_(False),
            ELIGIBLE,
            ItemRef.kind.in_(kinds),
            ItemRef.value.in_(values),
        )
    ):
        carriers[(kind, value)].add(item_id)
    return {
        item_id: set().union(*(carriers[pair] for pair in refs)) - {item_id}
        for item_id, refs in own.items()
    }


def _news(
    session: Session, eligible: list[Row], scorer: Scorer, mentions: Mentions
) -> list[Candidate]:
    """Events reported by at least two sources, ranked by how many sources, then by how much the
    community talked about them (posts in the event, or posts sharing one of its articles)."""
    folds = [
        fold
        for fold in _fold_stories([r for r in eligible if r.item.track is Track.NEWS])
        if fold.story_id is not None
    ]
    stories = _stories(session, folds)
    folds = [
        fold
        for fold in folds
        if fold.story_id in stories and stories[fold.story_id].source_count >= MIN_NEWS_SOURCES
    ]
    leads = [_lead(fold, stories[fold.story_id]) for fold in folds if fold.story_id is not None]
    cards = _cards(session, [lead.item.id for lead in leads])
    drafts: list[Candidate] = []
    for fold, lead, ids in zip(folds, leads, mentions.of(folds), strict=True):
        assert fold.story_id is not None
        story = stories[fold.story_id]
        drafts.append(
            _draft(
                "news",
                fold,
                story,
                lead,
                cards.get(lead.item.id),
                metrics={"source_count": story.source_count, "community_mentions": len(ids)},
                score=float(story.source_count * 100 + len(ids) * 10 + mentions.best_z(ids)),
            )
        )
    return _finish("news", drafts)


def _product(
    session: Session,
    start: datetime,
    end: datetime,
    eligible: list[Row],
    scorer: Scorer,
    mentions: Mentions,
) -> list[Candidate]:
    """Launch events and items: how many sources report them, then how hot the community found
    them. A single source needs a clearly above-norm post to be worth listing."""
    launch = _signal_items(session, start, end, "launch")
    folds = _fold_stories([r for r in eligible if r.item.id in launch])
    stories = _stories(session, folds)
    leads = [_lead(fold, stories.get(fold.story_id or 0)) for fold in folds]
    cards = _cards(session, [lead.item.id for lead in leads])
    drafts: list[Candidate] = []
    for fold, lead, ids in zip(folds, leads, mentions.of(folds), strict=True):
        story = stories.get(fold.story_id or 0)
        sources = story.source_count if story is not None else 1
        z_sum = mentions.z_sum(ids)
        if sources < MIN_PRODUCT_SOURCES and z_sum < MIN_PRODUCT_Z:
            continue
        drafts.append(
            _draft(
                "product",
                fold,
                story,
                lead,
                cards.get(lead.item.id),
                metrics={
                    "source_count": sources,
                    "community_mentions": len(ids),
                    "community_z": z_sum,
                },
                score=sources * 100 + z_sum,
            )
        )
    return _finish("product", drafts)


def _oss(
    session: Session,
    start: datetime,
    end: datetime,
    eligible: list[Row],
    scorer: Scorer,
) -> list[Candidate]:
    """Repositories (and Hugging Face models) by their star velocity, lifted by how many other
    posts of the window point at the same one."""
    rows = [row for row in eligible if row.item.track is Track.OSS]
    scorer.add(rows)
    mentioned = _ref_mentions(session, start, end, [row.item.id for row in rows], OSS_REF_KINDS)
    cards = _cards(session, [row.item.id for row in rows])
    drafts: list[Candidate] = []
    for row in rows:
        count = len(mentioned.get(row.item.id, ()))
        z = scorer.z.get(row.item.id)
        if (z is None or z < MIN_OSS_Z) and count < MIN_OSS_MENTIONS:
            continue
        card = cards.get(row.item.id)
        drafts.append(
            Candidate(
                cid="",
                section="oss",
                key=f"item:{row.item.id}",
                item_ids=[row.item.id],
                title_ko=(card.title_ko if card is not None else None) or row.item.title,
                summary_ko=_summary(card),
                url=row.item.url,
                metrics={**scorer.metrics[row.item.id], "mentions": count},
                score=(z or 0.0) + count * OSS_MENTION_WEIGHT,
                stat_rank=0,
            )
        )
    return _finish("oss", drafts)


def _interview(
    session: Session, eligible: list[Row], scorer: Scorer, mentions: Mentions
) -> list[Candidate]:
    """Podcasts, newsletters and videos, and news whose headline is an interview or a talk;
    ranked by how many report on them and, for a video, how often it was watched."""
    rows = [
        row
        for row in eligible
        if row.category in INTERVIEW_CATEGORIES
        or (row.item.track is Track.NEWS and INTERVIEW_PATTERN.search(row.item.title))
    ]
    scorer.add([row for row in rows if row.operator == YOUTUBE])
    folds = _fold_stories(rows)
    stories = _stories(session, folds)
    leads = [_lead(fold, stories.get(fold.story_id or 0)) for fold in folds]
    cards = _cards(session, [lead.item.id for lead in leads])
    drafts: list[Candidate] = []
    for fold, lead, ids in zip(folds, leads, mentions.of(folds), strict=True):
        story = stories.get(fold.story_id or 0)
        reports = story.source_count if story is not None else 0
        views_z = max((scorer.z[r.item.id] for r in fold.rows if r.item.id in scorer.z), default=0)
        drafts.append(
            _draft(
                "interview",
                fold,
                story,
                lead,
                cards.get(lead.item.id),
                metrics={
                    **scorer.metrics.get(lead.item.id, {}),
                    "source_count": reports,
                    "mentions": len(ids),
                },
                score=views_z + reports + len(ids),
            )
        )
    return _finish("interview", drafts)


def _research(
    session: Session,
    start: datetime,
    end: datetime,
    eligible: list[Row],
    scorer: Scorer,
) -> list[Candidate]:
    """Papers that news or the community pointed at (by DOI or arXiv id), or that Hugging Face's
    daily papers readers voted up."""
    rows = [row for row in eligible if row.item.track is Track.RESEARCH_IP]
    scorer.add([row for row in rows if row.operator == HF_PAPERS])
    mentioned = _ref_mentions(
        session, start, end, [row.item.id for row in rows], RESEARCH_REF_KINDS
    )
    cards = _cards(session, [row.item.id for row in rows])
    drafts: list[Candidate] = []
    for row in rows:
        count = len(mentioned.get(row.item.id, ()))
        metrics = scorer.metrics.get(row.item.id, {})
        upvotes = metrics.get("upvotes")
        upvotes = upvotes if isinstance(upvotes, int) else 0
        if count < 1 and upvotes < MIN_HF_UPVOTES:
            continue
        card = cards.get(row.item.id)
        drafts.append(
            Candidate(
                cid="",
                section="research",
                key=f"item:{row.item.id}",
                item_ids=[row.item.id],
                title_ko=(card.title_ko if card is not None else None) or row.item.title,
                summary_ko=_summary(card),
                url=row.item.url,
                metrics={**metrics, "mentions": count, "upvotes": upvotes},
                score=count * RESEARCH_MENTION_WEIGHT + scorer.z.get(row.item.id, 0.0),
                stat_rank=0,
            )
        )
    return _finish("research", drafts)


def _patent(
    session: Session,
    start: datetime,
    end: datetime,
    eligible: list[Row],
    scorer: Scorer,
    mentions: Mentions,
) -> list[Candidate]:
    """Events the cards mark as intellectual property, and patent-office publications that
    someone talked about; ranked by reports plus mentions."""
    ip = _signal_items(session, start, end, "ip")
    folds = _fold_stories([r for r in eligible if r.item.id in ip or r.category == PATENT_OFFICE])
    stories = _stories(session, folds)
    leads = [_lead(fold, stories.get(fold.story_id or 0)) for fold in folds]
    cards = _cards(session, [lead.item.id for lead in leads])
    drafts: list[Candidate] = []
    for fold, lead, ids in zip(folds, leads, mentions.of(folds), strict=True):
        story = stories.get(fold.story_id or 0)
        reports = story.source_count if story is not None else 1
        marked = any(row.item.id in ip for row in fold.rows)
        if reports < 1 or (not marked and not ids):
            continue
        drafts.append(
            _draft(
                "patent",
                fold,
                story,
                lead,
                cards.get(lead.item.id),
                metrics={"source_count": reports, "mentions": len(ids)},
                score=float(reports + len(ids)),
            )
        )
    return _finish("patent", drafts)


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
    (the freeze time), which is also when velocity is measured; `now` is when the freeze runs.
    Engagement is scored only for the rows a section ranks by it."""
    start, end = window(day)
    eligible = _eligible_items(session, start, end)
    scorer = Scorer(session, at=end)
    mentions = Mentions(session, start, end, eligible, scorer)
    return {
        "news": _news(session, eligible, scorer, mentions),
        "product": _product(session, start, end, eligible, scorer, mentions),
        "oss": _oss(session, start, end, eligible, scorer),
        "interview": _interview(session, eligible, scorer, mentions),
        "community": _community(session, eligible, scorer),
        "research": _research(session, start, end, eligible, scorer),
        "patent": _patent(session, start, end, eligible, scorer, mentions),
    }
