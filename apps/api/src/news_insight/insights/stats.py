"""Daily research and patent counts (plan 19 §2.3) for the 연구 and 특허 menus.

A document's day is the KST date of its own date, coalesce(published_at, first_seen_at)
(Item.occurred_at). Each day is rebuilt in one pass (delete its rows, insert the new ones), so a
rebuild is idempotent and follows late cards, enrichment and registry edits. The scheduler
rebuilds yesterday and the two days before at 03:40 KST; `news-insight insights backfill-stats`
rebuilds a longer stretch once.

Counted like the reader counts: no canary items, no repeats of an earlier item, no archive pages
(content/freshness.py). A document without a ready card is counted under field "other".

research_daily_stats rows (dim → key column): total, theme (field = the theme's own field),
company (registry key), org (institution name, not linked to a company, with its OpenAlex
type), country. patent_daily_stats rows: total, company, office, each per field and source.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, exists, func, insert, select, union
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item, ItemDedup
from news_insight.patents.models import PatentDailyStat, PatentMeta
from news_insight.research.models import EnrichStatus, ResearchDailyStat, ResearchMeta
from news_insight.research.service import research_documents
from news_insight.sources.models import Source
from news_insight.taxonomy.catalog import FIELD_KEYS

KST = ZoneInfo("Asia/Seoul")
OTHER = "other"
RECENT_DAYS = 3
CHANGED_WITHIN = timedelta(hours=25)  # a day between runs, with an hour to spare
ORG_TYPE_MAX = 20


@dataclass
class StatsResult:
    days: list[date] = field(default_factory=list)
    research_rows: int = 0
    patent_rows: int = 0


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a KST day, in UTC."""
    start = datetime.combine(day, time(), tzinfo=KST)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def recent_days(now: datetime, days: int = RECENT_DAYS) -> list[date]:
    """The `days` KST days before today, oldest first (yesterday last)."""
    today = now.astimezone(KST).date()
    return [today - timedelta(days=back) for back in range(days, 0, -1)]


def _field(value: str | None) -> str:
    return value if value in FIELD_KEYS else OTHER


def _ready_card() -> Any:
    return and_(ItemCard.item_id == Item.id, ItemCard.status == CardStatus.READY)


def _in_day(day: date) -> list[Any]:
    start, end = day_bounds(day)
    return [Item.occurred_at >= start, Item.occurred_at < end]


def _research_rows(session: Session, day: date) -> list[dict[str, Any]]:
    docs = session.execute(
        select(
            ItemCard.field,
            ItemCard.themes,
            ResearchMeta.institutions,
            ResearchMeta.countries,
            ResearchMeta.company_keys,
            ResearchMeta.has_company,
        )
        .select_from(Item)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, _ready_card())
        .outerjoin(ResearchMeta, ResearchMeta.item_id == Item.id)
        .where(*research_documents(), fresh_condition(), *_in_day(day))
    ).all()
    counts: Counter[tuple[str, str, str, str, str, str]] = Counter()
    company_counts: Counter[tuple[str, str, str, str, str, str]] = Counter()
    org_types: dict[tuple[str, str, str, str, str, str], str] = {}
    for card_field, themes, institutions, countries, company_keys, has_company in docs:
        doc_field = _field(card_field)
        keys: set[tuple[str, str, str, str, str, str]] = {("total", doc_field, "", "", "", "")}
        for theme in themes or []:
            theme_field = str(theme).split("__", 1)[0]
            if theme_field in FIELD_KEYS:
                keys.add(("theme", theme_field, str(theme), "", "", ""))
        keys.update(("company", doc_field, "", key, "", "") for key in company_keys or [])
        for institution in institutions or []:
            if institution.get("company_key") or not institution.get("name"):
                continue
            key = ("org", doc_field, "", "", str(institution["name"]), "")
            keys.add(key)
            org_types.setdefault(key, str(institution.get("type") or "")[:ORG_TYPE_MAX])
        keys.update(("country", doc_field, "", "", "", country) for country in countries or [])
        for key in keys:
            counts[key] += 1
            if has_company:
                company_counts[key] += 1
    columns = ("dim", "field", "theme", "company_key", "org_name", "country")
    return [
        {
            "day": day,
            **dict(zip(columns, key, strict=True)),
            "org_type": org_types.get(key, ""),
            "n": n,
            "n_company": company_counts[key],
        }
        for key, n in counts.items()
    ]


def _patent_rows(session: Session, day: date) -> list[dict[str, Any]]:
    docs = session.execute(
        select(PatentMeta.field, PatentMeta.source, PatentMeta.company_keys, PatentMeta.office)
        .join(Item, Item.id == PatentMeta.item_id)
        .where(
            Item.canary.is_(False),
            ~exists().where(ItemDedup.item_id == Item.id, ItemDedup.duplicate_of.is_not(None)),
            fresh_condition(),
            *_in_day(day),
        )
    ).all()
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    for doc_field, source, company_keys, office in docs:
        doc_field, kind = _field(doc_field), str(source)
        keys = {("total", doc_field, kind, "", "")}
        keys.update(("company", doc_field, kind, key, "") for key in company_keys or [])
        if office:
            keys.add(("office", doc_field, kind, "", office))
        counts.update(keys)
    return [
        {
            "day": day,
            "dim": dim,
            "field": doc_field,
            "source": kind,
            "company_key": company_key,
            "office": office,
            "n": n,
        }
        for (dim, doc_field, kind, company_key, office), n in counts.items()
    ]


def recompute_days(session: Session, days: Iterable[date]) -> StatsResult:
    """Rebuild the given days of both tables."""
    result = StatsResult()
    for day in sorted(set(days)):
        research = _research_rows(session, day)
        patents = _patent_rows(session, day)
        session.execute(delete(ResearchDailyStat).where(ResearchDailyStat.day == day))
        session.execute(delete(PatentDailyStat).where(PatentDailyStat.day == day))
        if research:
            session.execute(insert(ResearchDailyStat), research)
        if patents:
            session.execute(insert(PatentDailyStat), patents)
        result.days.append(day)
        result.research_rows += len(research)
        result.patent_rows += len(patents)
    session.flush()
    return result


def changed_days(session: Session, *, since: datetime) -> list[date]:
    """KST days of the papers enriched and patents indexed since `since`: a new arXiv paper is
    usually not on OpenAlex yet and is found a week later, after its day was last rebuilt."""
    kst_day = func.date(func.timezone(KST.key, Item.occurred_at))
    research = (
        select(kst_day)
        .join(ResearchMeta, ResearchMeta.item_id == Item.id)
        .where(ResearchMeta.enriched_at >= since, ResearchMeta.status == EnrichStatus.OK)
    )
    patents = (
        select(kst_day)
        .join(PatentMeta, PatentMeta.item_id == Item.id)
        .where(PatentMeta.indexed_at >= since)
    )
    return sorted(set(session.scalars(union(research, patents))))


def recompute_recent(
    session: Session, *, now: datetime, changed_within: timedelta = CHANGED_WITHIN
) -> StatsResult:
    """The daily 03:40 rebuild: yesterday and the two days before (late cards), plus every
    earlier day with papers enriched or patents indexed since the previous run. Today is left
    out: its rows would be partial until tomorrow's run."""
    today = now.astimezone(KST).date()
    changed = changed_days(session, since=now - changed_within)
    return recompute_days(session, {*recent_days(now), *(d for d in changed if d < today)})
