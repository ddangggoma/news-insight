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


class RadarWindow(BaseModel):
    kind: str
    key: str
    start: datetime
    end: datetime
    prev_key: str
    next_key: str
    is_current: bool


class HotCell(BaseModel):
    field: str
    business: str
    count: int
    previous: int


class RadarKpis(BaseModel):
    total: int
    previous_total: int
    new_stories: int
    cross_track_stories: int
    hottest: HotCell | None


class Cell(BaseModel):
    field: str
    business: str
    count: int
    previous: int


class FieldMomentum(BaseModel):
    key: str
    counts: list[int]
    change: float | None


class HypePoint(BaseModel):
    """Chatter = news + community reports; research = papers + open source."""

    key: str
    chatter: int
    chatter_change: float | None
    research: int
    research_change: float | None


class KeywordShift(BaseModel):
    key: str
    label: str
    state: str
    counts: list[int]


class Radar(BaseModel):
    window: RadarWindow
    kpis: RadarKpis
    cells: list[Cell]
    momentum: list[FieldMomentum]
    hype: list[HypePoint]
    keywords: list[KeywordShift]


class KeywordCount(BaseModel):
    key: str
    label: str
    count: int


class CellDetail(BaseModel):
    field: str
    business: str
    count: int
    previous: int
    trend: list[int]
    themes: list[Count]
    keywords: list[KeywordCount]
    stories: list[ReaderItem]
