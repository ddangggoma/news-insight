"""Reader filters shared by the feed, facets and insights.

Values within one axis are OR-ed, axes are AND-ed. `conditions(skip=...)` leaves one axis out so
facet counts show what choosing another value on that axis would give.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement, Select, Text, cast, or_

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item
from news_insight.public.periods import Window
from news_insight.sources.enums import Region, Track
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.taxonomy import registry as taxonomy
from news_insight.taxonomy.catalog import TAXONOMY_TREE
from news_insight.taxonomy.query import parse_ref, under_nodes


def in_current_tree() -> ColumnElement[bool]:
    """Cards classified against the current tree, provisional mapping included."""
    return ItemCard.taxonomy_revision.like(f"{TAXONOMY_TREE}.%")


SCOPES = {"relevant": ("dx", "dx_dependency"), "dx": ("dx",), "all": None}
AXES = ("field", "theme", "signal", "impact", "track", "region")  # facet axes
COMPANY_KEY = re.compile(r"^[^\s]{2,80}$")  # registry keys are normalised (no spaces)
FIXED: dict[str, frozenset[str]] = {
    "track": frozenset(track.value for track in Track),
    "region": frozenset(region.value for region in Region),
}


def allowed(axis: str) -> frozenset[str]:
    """Taxonomy axes follow the current schemes (plan 15-4: nodes change in the console)."""
    if axis in FIXED:
        return FIXED[axis]
    registry = taxonomy.current()
    if axis in ("field", "theme"):
        tech = registry.scheme("technology")
        depth = 1 if axis == "field" else 2
        return frozenset(n.key for n in tech.nodes if n.depth == depth)
    scheme = {"signal": "signal_type", "impact": "impact"}[axis]
    return frozenset(registry.scheme(scheme).by_key) if scheme in registry.schemes else frozenset()


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
            if axis == "company":  # registry keys change in the console: checked by shape only
                unknown = [v for v in chosen if not COMPANY_KEY.match(v)]
            elif axis == "node":  # scheme:key of any scheme and depth, checked by shape
                unknown = [v for v in chosen if parse_ref(v) is None]
            else:
                unknown = [v for v in chosen if v not in allowed(axis)]
            if unknown:
                raise FilterError(f"unknown {axis} '{unknown[0]}'")
            if chosen:
                values[axis] = chosen
        query = (q or "").strip() or None
        return cls(scope=scope, values=values, q=query)

    def conditions(self, *, skip: str | None = None) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            ItemCard.status == CardStatus.READY,
            in_current_tree(),
            fresh_condition(),  # archive pages a sitemap found are not today's news
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
    if axis == "signal":
        return ItemCard.signal_type.in_(chosen)
    if axis == "impact":
        return ItemCard.impact.in_(chosen)
    if axis == "company":
        return or_(*(ItemCard.company_keys.contains([value]) for value in chosen))
    if axis == "node":
        return under_nodes(tuple(ref for v in chosen if (ref := parse_ref(v)) is not None))
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
        statement.select_from(Item)
        .join(Source, Source.id == Item.source_id)
        .join(ItemCard, ItemCard.item_id == Item.id)
        .outerjoin(StoryItem, StoryItem.item_id == Item.id)
        .outerjoin(Story, Story.id == StoryItem.story_id)
    )
