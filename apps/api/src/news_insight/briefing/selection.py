"""Freeze candidates and pick the daily shortlist under the publication balance rules (§8, D13)."""

import math
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item
from news_insight.digest.bundle import digest_window
from news_insight.sources.enums import STAGE_ORDER, Region, SourceStatus, Track, ValidationStage
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem

RELEVANT_SCOPES = ("dx", "dx_dependency")
OFFICIAL_CATEGORIES = frozenset({"official_vendor", "government", "research_org", "ip_office"})
INDEPENDENT_CATEGORIES = frozenset({"independent_media"})
MIN_STAGE = ValidationStage.V3


@dataclass(frozen=True)
class SelectionRules:
    size: int = 60
    track_min: dict[str, int] = field(
        default_factory=lambda: {"news": 30, "research_ip": 10, "oss": 6, "community": 8}
    )
    # blocking gate: the published shortlist must contain at least this many per track
    track_gate_min: dict[str, int] = field(
        default_factory=lambda: {"news": 10, "research_ip": 3, "oss": 2, "community": 3}
    )
    domain_cap: float = 0.08
    korean_min: float = 0.15
    official_min: float = 0.25
    independent_min: float = 0.25


@dataclass(frozen=True)
class Candidate:
    item_id: int
    track: str
    category: str
    region: str
    domain: str
    score: float

    @property
    def official(self) -> bool:
        return self.category in OFFICIAL_CATEGORIES

    @property
    def independent(self) -> bool:
        return self.category in INDEPENDENT_CATEGORIES


def eligible_items(session: Session, *, briefing_date: date) -> list[int]:
    """Previous KST day, carded, DX-relevant, story representative, healthy source."""
    start, end = digest_window(briefing_date)
    stages = STAGE_ORDER[STAGE_ORDER.index(MIN_STAGE) :]
    rows = session.execute(
        select(Item.id)
        .join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(Story, Story.id == StoryItem.story_id)
        .where(
            Item.first_seen_at >= start,
            Item.first_seen_at < end,
            ItemCard.status == CardStatus.READY,
            ItemCard.scope.in_(RELEVANT_SCOPES),
            Source.status != SourceStatus.PAUSED,
            Source.validation_stage.in_(stages),
            fresh_condition(),  # archive pages are not yesterday's news
            (StoryItem.item_id.is_(None)) | (Story.representative_item_id == Item.id),
        )
        .order_by(Item.id)
    ).scalars()
    return list(rows)


def load_candidates(session: Session, item_ids: list[int], *, now: datetime) -> list[Candidate]:
    if not item_ids:
        return []
    rows = session.execute(
        select(Item, Source, ItemCard, Story)
        .join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(Story, Story.id == StoryItem.story_id)
        .where(Item.id.in_(item_ids))
    ).tuples()
    candidates = []
    for item, source, card, story in rows:
        coverage = story.source_count if story is not None else 1
        relevance = card.relevance if card.relevance is not None else 50
        primary = 5 if source.validation_stage is ValidationStage.V6 else 0
        candidates.append(
            Candidate(
                item_id=item.id,
                track=item.track.value,
                category=source.category,
                region=source.region.value,
                domain=source.official_domain,
                score=relevance + 12 * math.log2(1 + coverage) + primary,
            )
        )
    candidates.sort(key=lambda c: (c.score, -c.item_id), reverse=True)
    return candidates


def shortlist(candidates: list[Candidate], rules: SelectionRules) -> list[Candidate]:
    """Greedy: satisfy each minimum with its best candidates, then fill by score; a domain
    never exceeds `domain_cap` of the target size."""
    cap = max(1, math.floor(rules.domain_cap * rules.size))
    chosen: list[Candidate] = []
    taken: set[int] = set()
    per_domain: dict[str, int] = {}

    def take(pool: list[Candidate], need: int) -> None:
        for candidate in pool:
            if need <= 0 or len(chosen) >= rules.size:
                return
            if candidate.item_id in taken or per_domain.get(candidate.domain, 0) >= cap:
                continue
            chosen.append(candidate)
            taken.add(candidate.item_id)
            per_domain[candidate.domain] = per_domain.get(candidate.domain, 0) + 1
            need -= 1

    def short(predicate_count: int, share: float) -> int:
        return max(0, math.ceil(share * rules.size) - predicate_count)

    take([c for c in candidates if c.region == Region.KR.value], short(0, rules.korean_min))
    take(
        [c for c in candidates if c.official],
        short(sum(c.official for c in chosen), rules.official_min),
    )
    take(
        [c for c in candidates if c.independent],
        short(sum(c.independent for c in chosen), rules.independent_min),
    )
    for track in Track:
        have = sum(c.track == track.value for c in chosen)
        take(
            [c for c in candidates if c.track == track.value],
            rules.track_min.get(track.value, 0) - have,
        )
    take(candidates, rules.size - len(chosen))
    order = {track.value: index for index, track in enumerate(Track)}
    return sorted(chosen, key=lambda c: (order[c.track], -c.score))
