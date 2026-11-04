"""The 연구 menu (plan 19 §1): papers by technology field, company or institution and country.

Counts come from research_daily_stats (insights/stats.py), the documents page's total too; the
documents themselves and the watched-company count are read live with the same document
conditions (research_documents, no archive pages). A paper's 화제 점수 is
10 × news and community items citing its DOI or arXiv id since the window began
+ its Hugging Face upvotes + 5 × ln(1 + citations)."""

from typing import Any, Literal

from sqlalchemy import ColumnElement, Integer, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item, ItemMetricSnapshot
from news_insight.public.domains import (
    OTHER,
    Coverage,
    Doc,
    Span,
    bucketed,
    company_refs,
    field_label,
    instants,
)
from news_insight.research.models import ResearchDailyStat, ResearchMeta
from news_insight.research.service import research_documents
from news_insight.sources.enums import Track
from news_insight.sources.models import Source
from news_insight.spotlight.candidates import HF_PAPERS, RESEARCH_REF_KINDS
from news_insight.stories.models import ItemRef
from news_insight.taxonomy.catalog import FIELD_KEYS

MENTION_WEIGHT = 10
CITATION_WEIGHT = 5
DOC_ORGS = 3
COUNTRY_LABELS = {
    "US": "미국",
    "CN": "중국",
    "KR": "한국",
    "JP": "일본",
    "TW": "대만",
    "DE": "독일",
    "GB": "영국",
    "FR": "프랑스",
    "CA": "캐나다",
    "IN": "인도",
    "IT": "이탈리아",
    "ES": "스페인",
    "NL": "네덜란드",
    "CH": "스위스",
    "SE": "스웨덴",
    "AU": "호주",
    "SG": "싱가포르",
    "HK": "홍콩",
    "IL": "이스라엘",
    "BR": "브라질",
    "RU": "러시아",
    "AT": "오스트리아",
    "BE": "벨기에",
    "DK": "덴마크",
    "FI": "핀란드",
    "NO": "노르웨이",
    "PL": "폴란드",
    "IE": "아일랜드",
    "SA": "사우디아라비아",
    "AE": "아랍에미리트",
    "TR": "튀르키예",
    "IR": "이란",
    "VN": "베트남",
    "MY": "말레이시아",
    "PT": "포르투갈",
    "GR": "그리스",
    "CZ": "체코",
    "MX": "멕시코",
}


def _window(window: Span) -> list[ColumnElement[bool]]:
    start, end = instants(window)
    return [
        *research_documents(),
        fresh_condition(),
        Item.occurred_at >= start,
        Item.occurred_at < end,
    ]


def _ready_card() -> ColumnElement[bool]:
    return and_(ItemCard.item_id == Item.id, ItemCard.status == CardStatus.READY)


def _card_field(field: str) -> ColumnElement[bool]:
    if field == OTHER:
        return or_(ItemCard.field.is_(None), ItemCard.field.not_in(sorted(FIELD_KEYS)))
    return ItemCard.field == field


def _scoped(statement: Any) -> Any:
    return (
        statement.select_from(Item)
        .join(Source, Source.id == Item.source_id)
        .outerjoin(ItemCard, _ready_card())
        .outerjoin(ResearchMeta, ResearchMeta.item_id == Item.id)
    )


class ResearchDomain:
    name: Literal["research"] = "research"
    model = ResearchDailyStat
    region_dim: Literal["country"] = "country"
    has_orgs = True

    def region_column(self) -> Any:
        return ResearchDailyStat.country

    def region_label(self, key: str) -> str:
        return COUNTRY_LABELS.get(key, key)

    def coverage(self, session: Session, window: Span) -> Coverage | None:
        return None

    def company_share(self, session: Session, window: Span, total: int) -> tuple[float | None, int]:
        stat = ResearchDailyStat
        docs = int(
            session.scalar(
                select(func.coalesce(func.sum(stat.n_company), 0)).where(
                    stat.dim == "total", stat.day >= window.start, stat.day <= window.end
                )
            )
            or 0
        )
        return (round(docs / total, 3) if total else None), docs

    def watched_count(self, session: Session, window: Span, watched: list[str]) -> int:
        if not watched:
            return 0
        return int(
            session.scalar(
                select(func.count())
                .select_from(ResearchMeta)
                .join(Item, Item.id == ResearchMeta.item_id)
                .join(Source, Source.id == Item.source_id)
                .where(ResearchMeta.company_keys.overlap(watched), *_window(window))
            )
            or 0
        )

    def themes(self, session: Session, field: str, windows: list[Span]) -> dict[str, list[int]]:
        stat = ResearchDailyStat
        # theme rows carry the theme's own field
        rows = bucketed(session, stat, "theme", windows, [stat.theme], stat.field == field)
        return {key: counts for (key,), counts in rows.items()}

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
    ) -> tuple[int, list[Doc]]:
        conditions = _window(window)
        if field is not None:
            conditions.append(_card_field(field))
        if company is not None:
            conditions.append(ResearchMeta.company_keys.contains([company]))
        if org is not None:
            conditions.append(ResearchMeta.institutions.contains([{"name": org}]))
        total = _stats_total(session, window, field=field, company=company, org=org)
        start, _ = instants(window)
        mentions = _mentions(start)
        upvotes = _upvotes(window)
        mention_count = func.coalesce(mentions.c.mentions, 0)
        score = (
            mention_count * MENTION_WEIGHT
            + func.coalesce(upvotes.c.upvotes, 0)
            + CITATION_WEIGHT * func.ln(1 + func.coalesce(ResearchMeta.cited_by, 0))
        ).label("score")
        rows = session.execute(
            _scoped(
                select(
                    Item.id,
                    Item.url,
                    Item.title,
                    Item.occurred_at,
                    Source.name.label("source_name"),
                    ItemCard.title_ko,
                    ItemCard.summary_ko,
                    ItemCard.field,
                    ResearchMeta.venue,
                    ResearchMeta.cited_by,
                    ResearchMeta.company_keys,
                    ResearchMeta.institutions,
                    mention_count.label("mentions"),
                    upvotes.c.upvotes,
                    score,
                )
            )
            .outerjoin(mentions, mentions.c.item_id == Item.id)
            .outerjoin(upvotes, upvotes.c.item_id == Item.id)
            .where(*conditions)
            .order_by(score.desc(), Item.occurred_at.desc(), Item.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        refs = company_refs(session, sorted({k for row in rows for k in row.company_keys or []}))
        docs = []
        for row in rows:
            companies = [refs[k] for k in row.company_keys or [] if k in refs]
            doc_field = row.field if row.field in FIELD_KEYS else OTHER
            orgs = list(
                dict.fromkeys(
                    str(i["name"])
                    for i in row.institutions or []
                    if i.get("name") and not i.get("company_key")
                )
            )
            docs.append(
                Doc(
                    id=row.id,
                    url=row.url,
                    title=row.title,
                    title_ko=row.title_ko,
                    summary=(row.summary_ko or [None])[0],
                    source_name=row.source_name,
                    occurred_at=row.occurred_at,
                    field=doc_field,
                    field_label=field_label(doc_field),
                    companies=companies,
                    watched=any(k in watched for k in row.company_keys or []),
                    score=round(float(row.score), 1),
                    venue=row.venue,
                    orgs=orgs[:DOC_ORGS],
                    cited_by=row.cited_by,
                    mentions=int(row.mentions),
                    upvotes=row.upvotes,
                )
            )
        return total, docs


def _stats_total(
    session: Session, window: Span, *, field: str | None, company: str | None, org: str | None
) -> int:
    """The documents matching the filters, from the daily stats: a live count would scan the
    window's papers a second time (tens of thousands a month)."""
    stat = ResearchDailyStat
    if company is not None:
        where = [stat.dim == "company", stat.company_key == company]
    elif org is not None:
        where = [stat.dim == "org", stat.org_name == org]
    else:
        where = [stat.dim == "total"]
    if field == OTHER:
        where.append(stat.field.not_in(sorted(FIELD_KEYS)))
    elif field is not None:
        where.append(stat.field == field)
    return int(
        session.scalar(
            select(func.coalesce(func.sum(stat.n), 0)).where(
                *where, stat.day >= window.start, stat.day <= window.end
            )
        )
        or 0
    )


def _mentions(since: Any) -> Any:
    """Per item: news and community items seen since `since` that cite one of its DOIs or arXiv
    ids. Starts from the citing items (few) and follows the (kind, value) index back."""
    cited, own, carrier = aliased(ItemRef), aliased(ItemRef), aliased(Item)
    return (
        select(
            own.item_id.label("item_id"), func.count(func.distinct(carrier.id)).label("mentions")
        )
        .select_from(cited)
        .join(carrier, carrier.id == cited.item_id)
        .join(
            own,
            and_(own.kind == cited.kind, own.value == cited.value, own.item_id != cited.item_id),
        )
        .where(
            cited.kind.in_(RESEARCH_REF_KINDS),
            carrier.track.in_((Track.NEWS, Track.COMMUNITY)),
            carrier.canary.is_(False),
            carrier.first_seen_at >= since,
        )
        .group_by(own.item_id)
        .subquery()
    )


def _upvotes(window: Span) -> Any:
    """Hugging Face daily papers of the window: their highest upvote count."""
    start, end = instants(window)
    value = ItemMetricSnapshot.metrics["upvotes"]
    number = case((func.jsonb_typeof(value) == "number", value.as_float()), else_=None)
    return (
        select(
            ItemMetricSnapshot.item_id.label("item_id"),
            cast(func.max(number), Integer).label("upvotes"),
        )
        .join(Item, Item.id == ItemMetricSnapshot.item_id)
        .join(Source, Source.id == Item.source_id)
        .where(Source.operator == HF_PAPERS, Item.occurred_at >= start, Item.occurred_at < end)
        .group_by(ItemMetricSnapshot.item_id)
        .subquery()
    )
