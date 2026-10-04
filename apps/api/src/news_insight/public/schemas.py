"""Reader-facing response models: no source keys, validation state or stored bodies."""

from datetime import date, datetime

from pydantic import BaseModel

from news_insight.digest.models import DigestStatus
from news_insight.digest.schemas import DigestContent, DigestItemRef


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
    elapsed: float | None  # share of the current window already past (None when closed)


class RadarKpis(BaseModel):
    """Per window, oldest first. `research` = research + open source items."""

    items: list[int]
    stories: list[int]
    sources: list[int]
    research: list[int]
    new_stories: int
    cross_track_stories: int


class Topic(BaseModel):
    """A field, theme or keyword: counts per window and the current window's breakdowns."""

    key: str
    label: str | None
    field: str | None
    counts: list[int]
    change: float | None
    z: float
    state: str | None  # new · surging · rising · steady · falling
    sources: int
    tracks: dict[str, int]
    previous_tracks: dict[str, int]
    impacts: dict[str, int]
    regions: dict[str, int]  # current window, by source region
    first_seen: dict[str, datetime]  # earliest report per region over the trend span
    official: int  # current-window reports from official vendor sources
    effective_sources: float | None  # 1 / HHI of reports per source in the current window


class KeywordPair(BaseModel):
    a: str
    b: str
    count: int
    lift: float
    is_new: bool


class FlowLink(BaseModel):
    source: str
    target: str
    count: int
    median_hours: float


class Flows(BaseModel):
    """Track-to-track hand-offs completed in the window (stories and shared identifiers)."""

    chains: int
    origins: dict[str, int]
    links: list[FlowLink]


class Radar(BaseModel):
    window: RadarWindow
    periods: list[str]
    kpis: RadarKpis
    fields: list[Topic]
    themes: list[Topic]
    keywords: list[Topic]
    pairs: list[KeywordPair]
    flows: Flows


class KeywordCount(BaseModel):
    key: str
    label: str
    count: int


class TopicDetail(BaseModel):
    kind: str
    topic: Topic
    themes: list[Count]
    keywords: list[KeywordCount]
    businesses: list[Count]
    regions: list[Count]
    stories: list[ReaderItem]


class PublicDigest(BaseModel):
    """A published digest without its model, cost or error fields."""

    digest_date: date
    version: int
    status: DigestStatus
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    item_count: int
    content: DigestContent
    items: list[DigestItemRef]
