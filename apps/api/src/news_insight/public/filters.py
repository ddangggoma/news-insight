"""Reader filters shared by the feed, facets and insights.

Values within one axis are OR-ed, axes are AND-ed. `conditions(skip=...)` leaves one axis out so
facet counts show what choosing another value on that axis would give.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement, Select, Text, cast, or_

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.public.periods import Window
from news_insight.sources.enums import Region, Track
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.taxonomy.catalog import (
    BUSINESS_KEYS,
    FIELD_KEYS,
    IMPACT_KEYS,
    TAXONOMY_REVISION,
    THEME_KEYS,
)

SCOPES = {"relevant": ("dx", "dx_dependency"), "dx": ("dx",), "all": None}
AXES = ("field", "theme", "business", "impact", "track", "region")
ALLOWED: dict[str, frozenset[str]] = {
    "field": FIELD_KEYS,
    "theme": THEME_KEYS,
    "business": BUSINESS_KEYS,
    "impact": IMPACT_KEYS,
    "track": frozenset(track.value for track in Track),
    "region": frozenset(region.value for region in Region),
}


class FilterError(ValueError):
    """A filter value the taxonomy or enums do not define."""


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True)
class ReaderFilters:
    scope: str = "relevant"
    values: dict[str, tuple[str, ...]] = field(default_factory=dict)
    q: str | None = None

    @classmethod
    def build(cls, *, scope: str, q: str | None, **axes: list[str] | None) -> "ReaderFilters":
        if scope not in SCOPES:
            raise FilterError(f"unknown scope '{scope}' (expected {', '.join(SCOPES)})")
        values: dict[str, tuple[str, ...]] = {}
        for axis, raw in axes.items():
            chosen = tuple(dict.fromkeys(v for v in raw or [] if v))
            unknown = [v for v in chosen if v not in ALLOWED[axis]]
            if unknown:
                raise FilterError(f"unknown {axis} '{unknown[0]}'")
            if chosen:
                values[axis] = chosen
        query = (q or "").strip() or None
        return cls(scope=scope, values=values, q=query)

    def conditions(self, *, skip: str | None = None) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            ItemCard.status == CardStatus.READY,
            ItemCard.taxonomy_revision == TAXONOMY_REVISION,
        ]
        scopes = SCOPES[self.scope]
        if scopes is not None:
            conditions.append(ItemCard.scope.in_(scopes))
        for axis, chosen in self.values.items():
            if axis != skip:
                conditions.append(_axis_condition(axis, chosen))
        if self.q:
            pattern = _like(self.q)
            conditions.append(
                or_(
                    ItemCard.title_ko.ilike(pattern, escape="\\"),
                    Item.title.ilike(pattern, escape="\\"),
                    cast(ItemCard.keywords, Text).ilike(pattern, escape="\\"),
                )
            )
        return conditions


def _axis_condition(axis: str, chosen: tuple[str, ...]) -> ColumnElement[bool]:
    if axis == "field":
        return ItemCard.field.in_(chosen)
    if axis == "theme":
        return or_(*(ItemCard.themes.contains([value]) for value in chosen))
    if axis == "business":
        return or_(*(ItemCard.businesses.contains([value]) for value in chosen))
    if axis == "impact":
        return ItemCard.impact.in_(chosen)
    if axis == "track":
        return Item.track.in_([Track(value) for value in chosen])
    return Source.region.in_([Region(value) for value in chosen])


def in_window(window: Window) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Item.first_seen_at < window.end]
    if window.start is not None:
        conditions.append(Item.first_seen_at >= window.start)
    return conditions


def joined[T: tuple[Any, ...]](statement: Select[T]) -> Select[T]:
    """Item ⋈ Source ⋈ ItemCard, with the item's story when it has one."""
    return (
        statement.join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(Story, Story.id == StoryItem.story_id)
    )
