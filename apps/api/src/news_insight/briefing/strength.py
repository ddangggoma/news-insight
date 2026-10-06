"""How well an insight or claim is supported (plan 13 B2): a grade from its evidence, no LLM.

The grade reads the cited items only: how many outlets carried the story (the widest story
among them counts), whether it spread across tracks (research, open source, community, news)
or regions, and how much of it is a vendor's own announcement. Nineteen outlets on three
continents and one press release are no longer shown with the same weight.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem

VENDOR = "official_vendor"
STRONG_OUTLETS = 5
WEAK_OUTLETS = 2
VENDOR_HEAVY = 0.5


class Strength(BaseModel):
    grade: str  # strong · medium · weak
    outlets: int
    tracks: int
    regions: int
    vendor_share: float
    reason: str


@dataclass(frozen=True)
class Evidence:
    source_id: int
    track: str
    region: str
    category: str
    story_sources: int


def evidence_for(session: Session, item_ids: Iterable[int]) -> dict[int, Evidence]:
    ids = list(dict.fromkeys(item_ids))
    if not ids:
        return {}
    rows = session.execute(
        select(Item.id, Item.source_id, Item.track, Source.region, Source.category, Story)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(Story, Story.id == StoryItem.story_id)
        .where(Item.id.in_(ids))
    ).tuples()
    return {
        int(item_id): Evidence(
            source_id=int(source_id),
            track=track.value,
            region=region.value,
            category=str(category),
            story_sources=story.source_count if story is not None else 1,
        )
        for item_id, source_id, track, region, category, story in rows
    }


def grade(item_ids: Iterable[int], evidence: dict[int, Evidence]) -> Strength | None:
    cited = [evidence[i] for i in dict.fromkeys(item_ids) if i in evidence]
    if not cited:
        return None
    outlets = max(len({e.source_id for e in cited}), max(e.story_sources for e in cited))
    tracks = len({e.track for e in cited})
    regions = len({e.region for e in cited})
    vendor_share = round(sum(e.category == VENDOR for e in cited) / len(cited), 2)
    if outlets <= WEAK_OUTLETS or vendor_share == 1.0:
        level = "weak"
    elif (
        outlets >= STRONG_OUTLETS and (tracks >= 2 or regions >= 2) and vendor_share < VENDOR_HEAVY
    ):
        level = "strong"
    else:
        level = "medium"
    parts = [f"출처 {outlets}곳", f"트랙 {tracks}개", f"권역 {regions}곳"]
    if vendor_share >= VENDOR_HEAVY:
        parts.append("자사 발표 중심")
    return Strength(
        grade=level,
        outlets=outlets,
        tracks=tracks,
        regions=regions,
        vendor_share=vendor_share,
        reason=" · ".join(parts),
    )
