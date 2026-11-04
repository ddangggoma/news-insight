"""The 연구 and 특허 menus (plan 19 §1, §4): one response per tab, built the same way for papers
and patents from their daily stats tables, with what the tables cannot answer read live.

Windows are rolling and end on `as_of`: the last KST day the daily counts were built
(stats_days), never later than yesterday — the counts leave today out until the next night's
run. A month is the 30 days up to as_of; the previous window is the same length just before it;
trends use a row of such windows (12 weeks, 12 months of 30 days, 9 quarters of 90 days) and flag
a series whose last window is two standard deviations above (rise) or below (fall) the eight
before. No z and no flag when a compared window starts before the first day counted, nor for
the enrichment-derived axes (country) while OpenAlex coverage of a past window is well below the
current one's: a backlog being filled is not a trend.

A domain (research.py, patents.py) supplies its stats model and the parts read elsewhere: theme
bars, the company share, watched-company documents, the documents page and the coverage note.
Live reads end on as_of too."""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Date, func, literal, select
from sqlalchemy.orm import Session

from news_insight.companies.catalog import CompanyStatus, Relation
from news_insight.companies.models import Company
from news_insight.companies.service import info_for
from news_insight.insights.models import DomainInsightRecord, InsightKind, InsightStatus, StatsDay
from news_insight.insights.stats import day_bounds
from news_insight.public.periods import KST
from news_insight.taxonomy.catalog import FIELD_KEYS, FIELDS, LABELS

Tab = Literal["overview", "fields", "companies", "trends", "documents"]
Period = Literal["week", "month", "quarter"]
Flag = Literal["rise", "fall"]
Entity = Literal["company", "org"]

PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 90}
TREND_WINDOWS = {"week": 12, "month": 12, "quarter": 9}
HEATMAP_WEEKS = 12
RISER_HISTORY = 4  # risers: the current window against the four before
FLAG_HISTORY = 8  # rise/fall flags: against the eight before
FLAG_Z = 2.0
MIN_FLAG = 3  # a rise needs at least 3 documents, a fall a mean of at least 3
RISERS = 5
TOP_SERIES = 8
RANKING = 30
TOP_DETAIL = 10
TOP_FIELDS = 3
WATCH_MAX = 20
PAGE_SIZE = 20
OTHER = "other"  # documents without a classified field
REST = "rest"  # the lines beyond the top 8, summed
REST_LABEL = "기타"
WATCHED = (Relation.SELF, Relation.COMPETITOR)
ENRICHMENT_RATIO = 0.8
INSIGHT_TABS = ("overview", "fields", "companies")
NOTE_SHORT = "비교할 과거 집계가 부족해 급증·급감을 표시하지 않음"
NOTE_ENRICHMENT = "과거 기간의 기관·국가 정보 보강률이 낮아 국가별 급증·급감을 표시하지 않음"


class UnknownField(ValueError):
    pass


class UnknownCompany(LookupError):
    pass


# ---------------------------------------------------------------- response


class Span(BaseModel):
    start: date
    end: date  # inclusive


class Option(BaseModel):
    key: str
    label: str


class DomainInsightSentence(BaseModel):
    text: str
    doc_ids: list[int]
    key: str | None = None  # the field or company a one-liner is about


class DomainInsight(BaseModel):
    """The daily Opus insight (plan 19 §3, P4): the latest published one up to today, with its
    date (the screen says so when it is not today's); null before the first."""

    date: date
    sentences: list[DomainInsightSentence]


class WindowCount(BaseModel):
    key: str
    label: str
    count: int
    previous: int
    change: float | None  # (count - previous) / previous; null when previous is 0


class Riser(BaseModel):
    key: str
    label: str
    count: int
    mean: float  # of the previous windows
    ratio: float | None
    z: float


class Kpis(BaseModel):
    count: int
    previous: int
    change: float | None
    rising_field: Riser | None
    company_share: float | None  # documents with a company author/applicant, of all
    company_docs: int
    watched_count: int  # documents of watched companies (self, competitor)
    watched_previous: int


class HeatmapRow(BaseModel):
    key: str
    label: str
    counts: list[int]  # one per week, oldest first


class Heatmap(BaseModel):
    weeks: list[Span]
    rows: list[HeatmapRow]
    max: int


class OverviewTab(BaseModel):
    kpis: Kpis
    heatmap: Heatmap
    risers: list[Riser]  # empty when the history does not reach back far enough
    coverage_note: str | None = None
    insight: DomainInsight | None = None


class CompanyOut(BaseModel):
    key: str
    label: str
    relation: str
    kind: str
    watched: bool


class OrgCount(BaseModel):
    name: str
    org_type: str
    count: int
    previous: int
    change: float | None


class Doc(BaseModel):
    id: int
    url: str
    title: str
    title_ko: str | None
    summary: str | None  # the card's first summary line
    source_name: str
    occurred_at: datetime
    field: str
    field_label: str
    companies: list[CompanyOut]
    watched: bool
    score: float
    # research
    venue: str | None = None
    orgs: list[str] = []  # institutions not linked to a registry company, author order
    cited_by: int | None = None
    cited_growth: int | None = None  # citations of as_of's year minus the year before
    mentions: int = 0  # news and community items citing its DOI or arXiv id, up to as_of
    upvotes: int | None = None  # Hugging Face daily papers
    # patents
    publication_number: str | None = None
    office: str | None = None
    patent_source: str | None = None  # ops | eps | news
    applicants: list[str] = []
    press: int = 0  # sources reporting it (its story)


class FieldDetail(BaseModel):
    key: str
    label: str
    count: int
    previous: int
    change: float | None
    themes: list[WindowCount]  # every theme of the field, busiest first
    series: list[int]  # per trend window (FieldsTab.buckets)
    companies: list["RankedCompany"]
    orgs: list[OrgCount]  # research only
    documents: list[Doc]
    insight: DomainInsight | None = None


class FieldsTab(BaseModel):
    items: list[WindowCount]  # the 12 fields in catalog order
    other: WindowCount  # unclassified documents
    selected: str
    buckets: list[Span]
    detail: FieldDetail


class RankedCompany(BaseModel):
    key: str  # registry key, or the institution name for an org
    label: str
    entity: Entity
    relation: str | None
    kind: str | None
    org_type: str | None  # OpenAlex institution type of an org
    watched: bool
    count: int
    previous: int
    change: float | None
    top_fields: list[WindowCount]


class WatchedCompany(BaseModel):
    company: CompanyOut
    count: int
    previous: int
    change: float | None
    fields: list[WindowCount]  # the current window's field mix
    series: list[int]  # per trend window


class WatchBlock(BaseModel):
    buckets: list[Span]
    total: int  # watched companies in the registry
    companies: list[WatchedCompany]  # those with documents, busiest first (20 at most)


class CompanyDetail(BaseModel):
    key: str
    label: str
    entity: Entity
    relation: str | None
    org_type: str | None
    watched: bool
    count: int
    previous: int
    change: float | None
    fields: list[WindowCount]
    series: list[int]  # per trend window (WatchBlock.buckets)
    documents: list[Doc]  # 최근 문헌: the 10 most recent of the window
    top_documents: list[Doc]  # the 10 best scored of the window


class CompaniesTab(BaseModel):
    kind: Entity  # research: 기업 (registry + company-type orgs) or 대학·연구기관
    ranking: list[RankedCompany]
    watch: WatchBlock
    detail: CompanyDetail | None
    insight: DomainInsight | None = None


class Series(BaseModel):
    key: str
    label: str
    counts: list[int]  # per trend window, oldest first
    current: int
    mean: float  # of the previous windows (up to 8)
    z: float | None  # null when the history is too short or too thinly enriched
    flag: Flag | None


class FlagOut(BaseModel):
    axis: Literal["field", "country", "office"]
    key: str
    label: str
    flag: Flag
    z: float
    current: int
    mean: float


class TrendsTab(BaseModel):
    buckets: list[Span]
    history: int
    fields: list[Series]  # top 8 and 기타
    regions_axis: Literal["country", "office"]
    regions: list[Series]  # top 8 and 기타
    flags: list[FlagOut]  # every field and region flagged, strongest first
    coverage_note: str | None = None  # why some flags are off


class DocumentsTab(BaseModel):
    page: int
    size: int
    total: int
    items: list[Doc]


class Coverage(BaseModel):
    """Which sources the patent counts of the window come from (the screen's data note)."""

    news: int
    eps: int
    ops: int
    note: str


class DomainView(BaseModel):
    kind: Literal["research", "patent"]
    tab: Tab
    period: Period
    as_of: date  # the last day counted: the last built, at most yesterday (KST)
    stats_from: date | None  # the first day counted
    window: Span
    previous: Span
    field: str | None
    company: str | None
    org: str | None
    field_options: list[Option]
    coverage: Coverage | None = None
    overview: OverviewTab | None = None
    fields: FieldsTab | None = None
    companies: CompaniesTab | None = None
    trends: TrendsTab | None = None
    documents: DocumentsTab | None = None


# ---------------------------------------------------------------- windows and numbers


@dataclass(frozen=True)
class StatsRange:
    first: date | None
    last: date | None


def stats_range(session: Session) -> StatsRange:
    first, last = session.execute(select(func.min(StatsDay.day), func.max(StatsDay.day))).one()
    return StatsRange(first=first, last=last)


def as_of(now: datetime, built: StatsRange) -> date:
    """The last day counted: yesterday (KST), or the last day built if the night's run has not
    happened yet."""
    yesterday = now.astimezone(KST).date() - timedelta(days=1)
    return min(yesterday, built.last) if built.last is not None else yesterday


def spans(end: date, days: int, count: int) -> list[Span]:
    """`count` windows of `days` days, the last one ending on `end`, oldest first."""
    return [
        Span(
            start=end - timedelta(days=days * (back + 1) - 1), end=end - timedelta(days=days * back)
        )
        for back in range(count - 1, -1, -1)
    ]


def instants(span: Span) -> tuple[datetime, datetime]:
    """[start, end) of a span in UTC, for live queries on Item.occurred_at."""
    return day_bounds(span.start)[0], day_bounds(span.end)[1]


def change(count: int, previous: int) -> float | None:
    return round((count - previous) / previous, 3) if previous else None


def zscore(counts: Sequence[int], history: int) -> tuple[float, float]:
    """(z of the last count against the `history` before it, their mean). The deviation is at
    least the Poisson one (√mean) and 1, so a quiet series does not flag on a couple of papers."""
    current, past = counts[-1], list(counts[-1 - history : -1])
    if not past:
        return 0.0, 0.0
    mean = sum(past) / len(past)
    deviation = math.sqrt(sum((x - mean) ** 2 for x in past) / len(past))
    return round((current - mean) / max(deviation, math.sqrt(mean), 1.0), 2), round(mean, 2)


def flag_of(counts: Sequence[int], history: int = FLAG_HISTORY) -> tuple[Flag | None, float, float]:
    z, mean = zscore(counts, history)
    if z >= FLAG_Z and counts[-1] >= MIN_FLAG:
        return "rise", z, mean
    if z <= -FLAG_Z and mean >= MIN_FLAG:
        return "fall", z, mean
    return None, z, mean


def field_label(key: str) -> str:
    if key == OTHER:
        return "미분류"
    return LABELS.get(key, key)


def check_field(field: str | None) -> None:
    """One of the 12 fields (the chips); unclassified documents are counted, not selectable."""
    if field is not None and field not in FIELD_KEYS:
        raise UnknownField(field)


def count_of(key: str, label: str, values: Sequence[int]) -> WindowCount:
    """A WindowCount from [..., previous, current]."""
    current, previous = values[-1], values[-2] if len(values) > 1 else 0
    return WindowCount(
        key=key, label=label, count=current, previous=previous, change=change(current, previous)
    )


# ---------------------------------------------------------------- stats queries


def bucketed(
    session: Session,
    model: Any,
    dim: str,
    windows: Sequence[Span],
    keys: Sequence[Any],
    *where: ColumnElement[bool],
) -> dict[tuple[str, ...], list[int]]:
    """Sum of n per key tuple and window (`windows` contiguous and of equal length), read with
    the (dim, day) index."""
    first, last = windows[0].start, windows[-1].end
    days = (windows[0].end - windows[0].start).days + 1
    back = (literal(last, Date) - model.day) // days  # whole windows before the last one
    inner = (
        select(back.label("back"), *keys, model.n.label("v"))
        .where(model.dim == dim, model.day >= first, model.day <= last, *where)
        .subquery()
    )
    key_columns = [inner.c[k.key] for k in keys]
    rows = session.execute(
        select(inner.c.back, *key_columns, func.sum(inner.c.v)).group_by(inner.c.back, *key_columns)
    ).all()
    out: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0] * len(windows))
    for back_value, *key, total in rows:
        index = len(windows) - 1 - int(back_value)
        if 0 <= index < len(windows):
            out[tuple(key)][index] += int(total or 0)
    return out


def top_keys(
    session: Session,
    model: Any,
    dim: str,
    window: Span,
    key: Any,
    limit: int,
    *where: ColumnElement[bool],
) -> list[str]:
    total = func.sum(model.n)
    rows = session.execute(
        select(key, total)
        .where(model.dim == dim, model.day >= window.start, model.day <= window.end, *where)
        .group_by(key)
        .order_by(total.desc(), key)
        .limit(limit)
    ).all()
    return [row[0] for row in rows]


def company_refs(session: Session, keys: Sequence[str]) -> dict[str, CompanyOut]:
    return {
        key: CompanyOut(
            key=key,
            label=info.name_ko or info.name,
            relation=info.relation,
            kind=info.kind,
            watched=info.relation in WATCHED,
        )
        for key, info in info_for(session, keys).items()
    }


def latest_insight(session: Session, kind: str, now: datetime) -> DomainInsightRecord | None:
    """The kind's latest published insight dated today (KST) or earlier."""
    return session.scalars(
        select(DomainInsightRecord)
        .where(
            DomainInsightRecord.kind == InsightKind(kind),
            DomainInsightRecord.status == InsightStatus.PUBLISHED,
            DomainInsightRecord.insight_date <= now.astimezone(KST).date(),
        )
        .order_by(DomainInsightRecord.insight_date.desc())
        .limit(1)
    ).first()


def _sentences(raw: Any, key_name: str | None = None) -> list[DomainInsightSentence]:
    out = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("text"), str):
            out.append(
                DomainInsightSentence(
                    text=entry["text"],
                    doc_ids=[i for i in entry.get("doc_ids") or [] if isinstance(i, int)],
                    key=entry.get(key_name) if key_name else None,
                )
            )
    return out


def _insight(
    row: DomainInsightRecord | None, part: str, key: str | None = None
) -> DomainInsight | None:
    """One part of a published insight for a tab: the overview sentences, the one-liner of a
    field (`key`), or the watched-company line and the company lines."""
    if row is None:
        return None
    payload = row.payload or {}
    if part == "overview":
        sentences = _sentences(payload.get("overview"))
    elif part == "field":
        sentences = [s for s in _sentences(payload.get("fields"), "field") if s.key == key]
    else:
        watch = payload.get("watch")
        sentences = (
            [DomainInsightSentence(text=watch, doc_ids=[])]
            if isinstance(watch, str) and watch.strip()
            else []
        )
        sentences += _sentences(payload.get("companies"), "company_key")
    return DomainInsight(date=row.insight_date, sentences=sentences) if sentences else None


def watched_keys(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(Company.key)
            .where(Company.relation.in_(WATCHED), Company.status != CompanyStatus.IGNORED)
            .order_by(Company.key)
        )
    )


# ---------------------------------------------------------------- the domain


@dataclass(frozen=True)
class Query:
    tab: Tab
    period: Period
    field: str | None
    company: str | None
    org: str | None
    kind: Entity
    page: int


class Domain(Protocol):
    """What differs between papers and patents."""

    @property
    def name(self) -> Literal["research", "patent"]: ...

    @property
    def model(self) -> Any: ...  # the daily stats table

    @property
    def region_dim(self) -> Literal["country", "office"]: ...

    @property
    def has_orgs(self) -> bool: ...

    @property
    def enrichment_regions(self) -> bool: ...  # regions come from OpenAlex enrichment

    def region_column(self) -> Any: ...

    def region_label(self, key: str) -> str: ...

    def company_share(
        self, session: Session, window: Span, total: int
    ) -> tuple[float | None, int]: ...

    def watched_count(self, session: Session, window: Span, watched: list[str]) -> int: ...

    def themes(self, session: Session, field: str, windows: list[Span]) -> dict[str, list[int]]: ...

    def documents(
        self,
        session: Session,
        window: Span,
        *,
        field: str | None,
        company: str | None,
        org: str | None,
        watched: list[str],
        page: int,
        size: int,
        recent: bool = False,
    ) -> tuple[int, list[Doc]]: ...

    def coverage(self, session: Session, window: Span) -> Coverage | None: ...


@dataclass
class Context:
    session: Session
    domain: Domain
    query: Query
    as_of: date
    days: int
    window: Span
    previous: Span
    trend: list[Span]
    watched: list[str]
    built: StatsRange
    _days: list[tuple[date, int, int]] | None = None

    def docs(
        self,
        *,
        size: int,
        page: int = 1,
        field: str | None = None,
        company: str | None = None,
        org: str | None = None,
        recent: bool = False,
    ) -> tuple[int, list[Doc]]:
        return self.domain.documents(
            self.session,
            self.window,
            field=field,
            company=company,
            org=org,
            watched=self.watched,
            page=page,
            size=size,
            recent=recent,
        )

    def history_ok(self, windows: Sequence[Span]) -> bool:
        """Every window lies within the days counted."""
        return self.built.first is not None and windows[0].start >= self.built.first

    def enrichment_ok(self, windows: Sequence[Span]) -> bool:
        """OpenAlex coverage of every earlier window is at least 80 % of the last window's."""
        if self._days is None:
            self._days = list(
                self.session.execute(
                    select(StatsDay.day, StatsDay.research_docs, StatsDay.research_enriched).where(
                        StatsDay.day >= windows[0].start, StatsDay.day <= windows[-1].end
                    )
                ).tuples()
            )

        def share(span: Span) -> float:
            rows = [r for r in self._days or [] if span.start <= r[0] <= span.end]
            docs = sum(r[1] for r in rows)
            return sum(r[2] for r in rows) / docs if docs else 0.0

        current = share(windows[-1])
        return all(share(span) >= ENRICHMENT_RATIO * current for span in windows[:-1])


def build_view(
    session: Session,
    domain: Domain,
    query: Query,
    *,
    now: datetime,
    built: StatsRange | None = None,
) -> DomainView:
    check_field(query.field)
    if query.company is not None and not info_for(session, [query.company]):
        raise UnknownCompany(query.company)
    built = built or stats_range(session)
    end = as_of(now, built)
    days = PERIOD_DAYS[query.period]
    trend = spans(end, days, TREND_WINDOWS[query.period])
    ctx = Context(
        session=session,
        domain=domain,
        query=query,
        as_of=end,
        days=days,
        window=trend[-1],
        previous=trend[-2],
        trend=trend,
        watched=watched_keys(session),
        built=built,
    )
    view = DomainView(
        kind=domain.name,
        tab=query.tab,
        period=query.period,
        as_of=end,
        stats_from=built.first,
        window=ctx.window,
        previous=ctx.previous,
        field=query.field,
        company=query.company,
        org=query.org,
        field_options=[Option(key=f.key, label=f.name) for f in FIELDS],
        coverage=domain.coverage(session, ctx.window),
    )
    insight = latest_insight(session, domain.name, now) if query.tab in INSIGHT_TABS else None
    if query.tab == "overview":
        view.overview = _overview(ctx)
        view.overview.insight = _insight(insight, "overview")
    elif query.tab == "fields":
        view.fields = _fields(ctx)
        view.fields.detail.insight = _insight(insight, "field", view.fields.selected)
    elif query.tab == "companies":
        view.companies = _companies(ctx)
        view.companies.insight = _insight(insight, "companies")
    elif query.tab == "trends":
        view.trends = _trends(ctx)
    else:
        total, items = ctx.docs(
            size=PAGE_SIZE,
            field=query.field,
            company=query.company,
            org=query.org,
            page=query.page,
        )
        view.documents = DocumentsTab(page=query.page, size=PAGE_SIZE, total=total, items=items)
    return view


def _field_counts(ctx: Context, windows: list[Span]) -> dict[str, list[int]]:
    model = ctx.domain.model
    rows = bucketed(ctx.session, model, "total", windows, [model.field])
    out: dict[str, list[int]] = {}
    for (key,), counts in rows.items():
        name = key if key in FIELD_KEYS else OTHER
        merged = out.setdefault(name, [0] * len(windows))
        for i, n in enumerate(counts):
            merged[i] += n
    return out


def _overview(ctx: Context) -> OverviewTab:
    session, domain = ctx.session, ctx.domain
    history = spans(ctx.as_of, ctx.days, RISER_HISTORY + 1)
    by_field = _field_counts(ctx, history)
    current = sum(c[-1] for c in by_field.values())
    previous = sum(c[-2] for c in by_field.values())
    risers = []
    history_ok = ctx.history_ok(history)
    for f in FIELDS if history_ok else ():
        counts = by_field.get(f.key, [0] * len(history))
        z, mean = zscore(counts, RISER_HISTORY)
        if counts[-1] > mean:
            risers.append(
                Riser(
                    key=f.key,
                    label=f.name,
                    count=counts[-1],
                    mean=mean,
                    ratio=round(counts[-1] / mean, 2) if mean else None,
                    z=z,
                )
            )
    risers.sort(key=lambda r: (r.z, r.ratio or 0, r.count), reverse=True)
    share, company_docs = domain.company_share(session, ctx.window, current)
    weeks = spans(ctx.as_of, 7, HEATMAP_WEEKS)
    weekly = _field_counts(ctx, weeks)
    rows = [
        HeatmapRow(key=f.key, label=f.name, counts=weekly.get(f.key, [0] * len(weeks)))
        for f in FIELDS
    ]
    return OverviewTab(
        kpis=Kpis(
            count=current,
            previous=previous,
            change=change(current, previous),
            rising_field=risers[0] if risers and risers[0].z >= FLAG_Z else None,
            company_share=share,
            company_docs=company_docs,
            watched_count=domain.watched_count(session, ctx.window, ctx.watched),
            watched_previous=domain.watched_count(session, ctx.previous, ctx.watched),
        ),
        heatmap=Heatmap(weeks=weeks, rows=rows, max=max((max(r.counts) for r in rows), default=0)),
        risers=risers[:RISERS],
        coverage_note=None if history_ok else NOTE_SHORT,
    )


def _top_fields(
    per_field: dict[str, list[int]], limit: int | None = TOP_FIELDS
) -> list[WindowCount]:
    counts = [count_of(key, field_label(key), values) for key, values in per_field.items()]
    counts = [c for c in counts if c.count > 0]
    counts.sort(key=lambda c: (-c.count, c.key))
    return counts if limit is None else counts[:limit]


def _per_field(
    rows: dict[tuple[str, ...], list[int]],
) -> dict[str, dict[str, list[int]]]:
    """{(key, field, ...): counts} → {key: {field: counts}}, unknown fields under OTHER."""
    out: dict[str, dict[str, list[int]]] = defaultdict(dict)
    for (key, field, *_), counts in rows.items():
        name = field if field in FIELD_KEYS else OTHER
        merged = out[key].setdefault(name, [0] * len(counts))
        for i, n in enumerate(counts):
            merged[i] += n
    return out


def _company_counts(
    ctx: Context, windows: list[Span], keys: list[str], *where: ColumnElement[bool]
) -> dict[str, dict[str, list[int]]]:
    """Per registry company, per field, the counts of `windows`."""
    model = ctx.domain.model
    if not keys:
        return {}
    return _per_field(
        bucketed(
            ctx.session,
            model,
            "company",
            windows,
            [model.company_key, model.field],
            model.company_key.in_(keys),
            *where,
        )
    )


def _org_counts(
    ctx: Context, windows: list[Span], names: list[str], *where: ColumnElement[bool]
) -> tuple[dict[str, dict[str, list[int]]], dict[str, str]]:
    """Per institution, per field, the counts of `windows`; and each one's OpenAlex type."""
    model = ctx.domain.model
    if not names:
        return {}, {}
    rows = bucketed(
        ctx.session,
        model,
        "org",
        windows,
        [model.org_name, model.field, model.org_type],
        model.org_name.in_(names),
        *where,
    )
    types: dict[str, str] = {}
    for name, _, org_type in rows:
        types[name] = max(types.get(name, ""), org_type or "")
    return _per_field(rows), types


def _sum(per_field: dict[str, list[int]], width: int) -> list[int]:
    total = [0] * width
    for counts in per_field.values():
        for i, n in enumerate(counts):
            total[i] += n
    return total


def _field_where(model: Any, field: str | None) -> list[ColumnElement[bool]]:
    return [] if field is None else [model.field == field]


def _field_filter(ctx: Context) -> list[ColumnElement[bool]]:
    return _field_where(ctx.domain.model, ctx.query.field)


def _fields(ctx: Context) -> FieldsTab:
    session, domain, model = ctx.session, ctx.domain, ctx.domain.model
    width = len(ctx.trend)
    by_field = _field_counts(ctx, ctx.trend)
    zero = [0] * width
    items = [count_of(f.key, f.name, by_field.get(f.key, zero)) for f in FIELDS]
    selected = ctx.query.field or max(items, key=lambda c: c.count).key
    series = by_field.get(selected, zero)
    pair = [ctx.previous, ctx.window]
    if selected in FIELD_KEYS:
        theme_counts = domain.themes(session, selected, pair)
        themes = [
            count_of(t.key, t.name, theme_counts.get(t.key, [0, 0]))
            for f in FIELDS
            if f.key == selected
            for t in f.themes
        ]
        themes.sort(key=lambda c: (-c.count, -c.previous))
    else:
        themes = []
    where = _field_where(model, selected)
    company_keys = top_keys(
        session, model, "company", ctx.window, model.company_key, TOP_DETAIL, *where
    )
    refs = company_refs(session, company_keys)
    per_company = _company_counts(ctx, pair, company_keys, *where)
    companies = [
        _ranked_company(key, refs[key], per_company.get(key, {}), 2)
        for key in company_keys
        if key in refs
    ]
    orgs: list[OrgCount] = []
    if domain.has_orgs:
        names = top_keys(session, model, "org", ctx.window, model.org_name, TOP_DETAIL, *where)
        per_org, types = _org_counts(ctx, pair, names, *where)
        for name in names:
            total = _sum(per_org.get(name, {}), 2)
            orgs.append(
                OrgCount(
                    name=name,
                    org_type=types.get(name, ""),
                    count=total[-1],
                    previous=total[-2],
                    change=change(total[-1], total[-2]),
                )
            )
    _, documents = ctx.docs(size=TOP_DETAIL, field=selected)
    current, previous = series[-1], series[-2]
    return FieldsTab(
        items=items,
        other=count_of(OTHER, field_label(OTHER), by_field.get(OTHER, zero)),
        selected=selected,
        buckets=ctx.trend,
        detail=FieldDetail(
            key=selected,
            label=field_label(selected),
            count=current,
            previous=previous,
            change=change(current, previous),
            themes=themes,
            series=series,
            companies=companies,
            orgs=orgs,
            documents=documents,
        ),
    )


def _ranked_company(
    key: str, ref: CompanyOut, per_field: dict[str, list[int]], width: int
) -> RankedCompany:
    total = _sum(per_field, width)
    return RankedCompany(
        key=key,
        label=ref.label,
        entity="company",
        relation=ref.relation,
        kind=ref.kind,
        org_type=None,
        watched=ref.watched,
        count=total[-1],
        previous=total[-2],
        change=change(total[-1], total[-2]),
        top_fields=_top_fields({k: v[-2:] for k, v in per_field.items()}),
    )


def _ranked_org(
    name: str, org_type: str, per_field: dict[str, list[int]], width: int
) -> RankedCompany:
    total = _sum(per_field, width)
    return RankedCompany(
        key=name,
        label=name,
        entity="org",
        relation=None,
        kind=None,
        org_type=org_type,
        watched=False,
        count=total[-1],
        previous=total[-2],
        change=change(total[-1], total[-2]),
        top_fields=_top_fields({k: v[-2:] for k, v in per_field.items()}),
    )


def _companies(ctx: Context) -> CompaniesTab:
    session, domain, model = ctx.session, ctx.domain, ctx.domain.model
    query = ctx.query
    kind: Entity = query.kind if domain.has_orgs else "company"
    where = _field_filter(ctx)
    pair = [ctx.previous, ctx.window]
    ranking: list[RankedCompany] = []
    if kind == "company":
        keys = top_keys(session, model, "company", ctx.window, model.company_key, RANKING, *where)
        refs = company_refs(session, keys)
        per_company = _company_counts(ctx, pair, keys, *where)
        ranking.extend(
            _ranked_company(key, refs[key], per_company.get(key, {}), 2)
            for key in keys
            if key in refs
        )
    if domain.has_orgs:
        is_company = model.org_type == "company"
        org_where = [*where, is_company if kind == "company" else ~is_company]
        names = top_keys(session, model, "org", ctx.window, model.org_name, RANKING, *org_where)
        per_org, types = _org_counts(ctx, pair, names, *org_where)
        ranking.extend(
            _ranked_org(name, types.get(name, ""), per_org.get(name, {}), 2) for name in names
        )
    ranking.sort(key=lambda c: (-c.count, -c.previous, c.label))

    width = len(ctx.trend)
    watched_refs = company_refs(session, ctx.watched)
    per_watched = _company_counts(ctx, ctx.trend, list(watched_refs))
    watched = []
    for key, ref in watched_refs.items():
        per_field = per_watched.get(key, {})
        series = _sum(per_field, width)
        if not any(series):
            continue
        watched.append(
            WatchedCompany(
                company=ref,
                count=series[-1],
                previous=series[-2],
                change=change(series[-1], series[-2]),
                fields=_top_fields({k: v[-2:] for k, v in per_field.items()}, limit=None),
                series=series,
            )
        )
    watched.sort(key=lambda w: (-w.count, -sum(w.series), w.company.key))

    detail = None
    if query.company is not None:
        company = company_refs(session, [query.company])[query.company]
        per_field = _company_counts(ctx, ctx.trend, [query.company]).get(query.company, {})
        detail = _detail(ctx, "company", company.key, company.label, per_field, company=company)
    elif query.org is not None and domain.has_orgs:
        per_org, types = _org_counts(ctx, ctx.trend, [query.org])
        per_field = per_org.get(query.org, {})
        if not any(_sum(per_field, width)):
            raise UnknownCompany(query.org)
        detail = _detail(ctx, "org", query.org, query.org, per_field, org_type=types[query.org])
    return CompaniesTab(
        kind=kind,
        ranking=ranking[:RANKING],
        watch=WatchBlock(buckets=ctx.trend, total=len(watched_refs), companies=watched[:WATCH_MAX]),
        detail=detail,
    )


def _detail(
    ctx: Context,
    entity: Entity,
    key: str,
    label: str,
    per_field: dict[str, list[int]],
    *,
    company: CompanyOut | None = None,
    org_type: str | None = None,
) -> CompanyDetail:
    series = _sum(per_field, len(ctx.trend))
    company_key, org = (key, None) if entity == "company" else (None, key)
    _, recent = ctx.docs(size=TOP_DETAIL, company=company_key, org=org, recent=True)
    _, top = ctx.docs(size=TOP_DETAIL, company=company_key, org=org)
    return CompanyDetail(
        key=key,
        label=label,
        entity=entity,
        relation=company.relation if company else None,
        org_type=org_type,
        watched=company.watched if company else False,
        count=series[-1],
        previous=series[-2],
        change=change(series[-1], series[-2]),
        fields=_top_fields({k: v[-2:] for k, v in per_field.items()}, limit=None),
        series=series,
        documents=recent,
        top_documents=top,
    )


def _series(key: str, label: str, counts: list[int], flagged: bool) -> Series:
    flag, z, mean = flag_of(counts)
    return Series(
        key=key,
        label=label,
        counts=counts,
        current=counts[-1],
        mean=mean,
        z=z if flagged else None,
        flag=flag if flagged else None,
    )


def _top_series(
    per_key: dict[str, list[int]],
    labels: dict[str, str],
    width: int,
    eligible: set[str] | None,
    flagged: bool,
) -> list[Series]:
    ranked = sorted(
        (k for k in per_key if eligible is None or k in eligible),
        key=lambda k: (-sum(per_key[k]), -per_key[k][-1], k),
    )
    top = ranked[:TOP_SERIES]
    rest = [0] * width
    for key, counts in per_key.items():
        if key not in top:
            for i, n in enumerate(counts):
                rest[i] += n
    out = [_series(k, labels.get(k, k), per_key[k], flagged) for k in top]
    if any(rest):
        out.append(_series(REST, REST_LABEL, rest, flagged))
    return out


def _trends(ctx: Context) -> TrendsTab:
    session, domain = ctx.session, ctx.domain
    width = len(ctx.trend)
    by_field = _field_counts(ctx, ctx.trend)
    labels = {f.key: f.name for f in FIELDS}
    history = min(FLAG_HISTORY, width - 1)
    compared = ctx.trend[-1 - history :]
    fields_flagged = ctx.history_ok(compared)
    regions_flagged = fields_flagged and (
        not domain.enrichment_regions or ctx.enrichment_ok(compared)
    )
    notes = [] if fields_flagged else [NOTE_SHORT]
    if fields_flagged and not regions_flagged:
        notes.append(NOTE_ENRICHMENT)
    fields = _top_series(by_field, labels, width, set(FIELD_KEYS), fields_flagged)
    region = domain.region_column()
    per_region = {
        key: counts
        for (key,), counts in bucketed(
            session, domain.model, domain.region_dim, ctx.trend, [region], *_field_filter(ctx)
        ).items()
        if key
    }
    region_labels = {key: domain.region_label(key) for key in per_region}
    regions = _top_series(per_region, region_labels, width, None, regions_flagged)
    flags: list[FlagOut] = []
    for axis, per_key, names, flagged in (
        ("field", {k: v for k, v in by_field.items() if k in FIELD_KEYS}, labels, fields_flagged),
        (domain.region_dim, per_region, region_labels, regions_flagged),
    ):
        for key, counts in per_key.items() if flagged else ():
            flag, z, mean = flag_of(counts)
            if flag is not None:
                flags.append(
                    FlagOut(
                        axis=axis,  # type: ignore[arg-type]
                        key=key,
                        label=names.get(key, key),
                        flag=flag,
                        z=z,
                        current=counts[-1],
                        mean=mean,
                    )
                )
    flags.sort(key=lambda f: (-abs(f.z), f.axis, f.key))
    return TrendsTab(
        buckets=ctx.trend,
        history=history,
        fields=fields,
        regions_axis=domain.region_dim,
        regions=regions,
        flags=flags,
        coverage_note=" · ".join(notes) or None,
    )
