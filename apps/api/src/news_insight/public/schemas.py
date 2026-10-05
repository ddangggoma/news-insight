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
    signal_types: list[TaxonomyNode]
    impacts: list[TaxonomyNode]
    scopes: list[TaxonomyNode]


class StoryBrief(BaseModel):
    id: int
    item_count: int
    source_count: int
    tracks: list[str]


class CompanyRef(BaseModel):
    key: str
    label: str
    relation: str  # to Samsung DX: self · competitor · supplier · partner · peer
    kind: str


class ReaderItem(BaseModel):
    id: int
    url: str
    title: str
    title_ko: str | None
    summary_ko: list[str]
    keywords: list[str]
    field: str | None
    themes: list[str]
    signal_type: str | None
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
    companies: list[CompanyRef] = []


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
    signal_types: list[Count]
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
    # window in progress: every window counted up to the same elapsed share; change, z and state
    # are scored on these (STAT-2). None for a closed window
    paced: list[int] | None = None
    change: float | None
    z: float
    state: str | None  # new · surging · rising · steady · falling
    sources: int
    tracks: dict[str, int]
    previous_tracks: dict[str, int]
    baseline_tracks: dict[str, int]  # summed over the windows before the current one
    impacts: dict[str, int]
    regions: dict[str, int]  # current window, by source region
    first_seen: dict[str, datetime]  # earliest report per region over the trend span
    official: int  # current-window reports from official vendor sources
    effective_sources: float | None  # 1 / HHI of reports per source in the current window
    capped: int = 0  # current-window reports, at most 3 per source and day (STAT-1)
    # mean share within each track (percent), so source-mix changes do not move it (STAT-1)
    normalized_share: float | None = None
    first_ever: datetime | None = None  # keywords only: first report ever (with the filters)
    returning: bool = False  # "new" in the span but seen before it
    debut: bool = False  # keywords only: first report ever within the last DEBUT_WINDOWS windows


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
    ref_kinds: dict[str, int] = {}  # chains carried by a shared identifier, per kind (SIG-1)


class KeywordCount(BaseModel):
    key: str
    label: str
    count: int


class EngagedItem(BaseModel):
    id: int
    title: str
    track: str
    source_name: str
    metric: str  # the metric that grew most
    gain: int
    current: int


class ThemeEngagement(BaseModel):
    key: str
    score: float  # sum over items of log(1 + gain) across metrics
    items: int  # items whose metrics grew in the window


class Engagement(BaseModel):
    """Reactions gained in the window (stars, points, likes …) from metric snapshots."""

    measured: int  # items with any growth
    themes: list[ThemeEngagement]
    top: list[EngagedItem]


class Anomaly(BaseModel):
    """One category far above its usual level for that weekday."""

    day: date
    field: str
    count: int
    expected: float  # mean of the same weekday over the previous four weeks
    z: float
    keywords: list[KeywordCount]  # in that category, most above their own baseline that day


class Calendar(BaseModel):
    """Reports per KST day, ending with the window, and per-category anomaly days."""

    start: date
    days: list[int]
    anomalies: list[Anomaly]


class FieldLink(BaseModel):
    a: str
    b: str
    count: int  # reports classified into both categories this window
    previous: int


class SignalFocus(BaseModel):
    kind: str  # field · theme · keyword
    key: str


class RadarSignal(BaseModel):
    """One card of the radar's rule-based reading (public/signals.py)."""

    tone: str  # surge · event · new · back · early · pull · shift · hype · thin · gap · link · cool
    title: str
    detail: str
    focus: SignalFocus
    score: float  # the rule's own test statistic, for ordering within a tone


class Radar(BaseModel):
    window: RadarWindow
    periods: list[str]
    kpis: RadarKpis
    fields: list[Topic]
    themes: list[Topic]
    keywords: list[Topic]
    pairs: list[KeywordPair]
    flows: Flows
    engagement: Engagement
    calendar: Calendar
    field_links: list[FieldLink]
    # first day of the current taxonomy tree: comparisons across it are indicative only
    taxonomy_revised_on: date | None = None
    signals: list[RadarSignal] = []


class CompanyProfile(BaseModel):
    """Registry entry of a company (plan 12)."""

    key: str
    name: str
    name_ko: str | None
    kind: str
    region: str
    relation: str
    themes: list[str]  # main themes in the registry


class TopicDetail(BaseModel):
    kind: str
    topic: Topic
    themes: list[Count]
    keywords: list[KeywordCount]
    signal_types: list[Count]
    regions: list[Count]
    stories: list[ReaderItem]
    # companies reported with this topic in the window (registered names only)
    companies: list[KeywordCount] = []
    # kind=theme: the registry's major companies of the theme; kind=company: none
    major_companies: list[CompanyRef] = []
    profile: CompanyProfile | None = None  # kind=company


class ActivityShift(BaseModel):
    """The signal type whose share of a company's reports moved most against the baseline."""

    signal_type: str
    share: float  # current window
    baseline_share: float  # earlier windows
    z: float  # two-proportion z


class CompanyTopic(Topic):
    name: str
    name_ko: str | None
    kind: str
    region: str
    relation: str
    self_reports: int  # current window, from the company's own domains
    signal_mix: dict[str, int]  # current window, by signal type
    baseline_mix: dict[str, int]  # earlier windows
    shift: ActivityShift | None
    top_themes: list[Count]  # current window


class LeaderShare(BaseModel):
    key: str
    label: str
    count: int
    share: float  # of the theme's company-tagged reports this window (percent)
    previous_share: float | None


class ThemeLeaders(BaseModel):
    theme: str
    total: int  # company-tagged reports this window
    previous_total: int
    leaders: list[LeaderShare]
    previous_leader: str | None
    leader_changed: bool


class ThemeEntry(BaseModel):
    """A company reported in a theme for the first time in the span, outside its main themes."""

    key: str
    label: str
    theme: str
    count: int
    sources: int


class Entrant(BaseModel):
    """A company first reported recently: registered (debut) or a name the registry lacks."""

    key: str
    name: str
    registered: bool
    cards: int
    sources: int
    first_seen: datetime | None = None


class CompanyPair(BaseModel):
    a: str
    b: str
    count: int
    lift: float
    is_new: bool
    signal_type: str | None  # most common signal type of the pair's reports


class CompanyRadar(BaseModel):
    window: RadarWindow
    periods: list[str]
    tagged: list[int]  # company-tagged reports per window
    companies: list[CompanyTopic]
    organizations: list[CompanyTopic]  # institutes, regulators, standards bodies
    theme_leaders: list[ThemeLeaders]
    entries: list[ThemeEntry]
    entrants: list[Entrant]
    pairs: list[CompanyPair]
    signals: list[RadarSignal] = []


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
