"""Reader-facing response models: no source keys, validation state or stored bodies."""

from datetime import datetime

from pydantic import BaseModel


class TaxonomyNode(BaseModel):
    key: str
    label: str


class TaxonomyField(TaxonomyNode):
    themes: list[TaxonomyNode]


class TaxonomyOut(BaseModel):
    revision: str
    fields: list[TaxonomyField]
    businesses: list[TaxonomyNode]
    impacts: list[TaxonomyNode]
    scopes: list[TaxonomyNode]


class StoryBrief(BaseModel):
    id: int
    item_count: int
    source_count: int
    tracks: list[str]


class ReaderItem(BaseModel):
    id: int
    url: str
    title: str
    title_ko: str | None
    summary_ko: list[str]
    keywords: list[str]
    field: str | None
    themes: list[str]
    businesses: list[str]
    impact: str | None
    scope: str | None
    relevance: int | None
    track: str
    source_name: str
    region: str
    published_at: datetime | None
    first_seen_at: datetime
    metrics: dict[str, int]
    story: StoryBrief | None


class FeedPage(BaseModel):
    """One row per story; `items_total` counts every matching report."""

    items: list[ReaderItem]
    total: int
    items_total: int
    page: int
    size: int


class LinkedItem(BaseModel):
    id: int
    url: str
    title: str
    title_ko: str | None
    track: str
    source_name: str
    first_seen_at: datetime
    ref: str | None = None


class ReaderItemDetail(BaseModel):
    item: ReaderItem
    story_items: list[LinkedItem]
    signals: list[LinkedItem]
    same_field: list[LinkedItem]


class Count(BaseModel):
    key: str
    count: int


class KeywordTrend(BaseModel):
    key: str
    label: str
    count: int
    previous: int | None
    change: float | None
    is_new: bool


class Insights(BaseModel):
    total: int
    previous_total: int | None
    keywords: list[KeywordTrend]
    related_keywords: list[str]
    fields: list[Count]
    businesses: list[Count]
    impacts: list[Count]
