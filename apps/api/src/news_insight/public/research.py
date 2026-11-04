"""The 연구 menu (plan 19 §1): papers by technology field, company or institution and country.

Counts come from research_daily_stats; the documents (주목 문헌, field and company details) and
the watched-company count come from research_signals, which the nightly job rebuilds after the
counts up to the same as_of (insights/signals.py): an indexed read of the window, never a scan of
the corpus. Listings of one paper are folded there: only each group's lead is listed."""

from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.models import Item
from news_insight.public.domains import (
    Coverage,
    Doc,
    Span,
    bucketed,
    company_refs,
    field_label,
)
from news_insight.research.models import ResearchDailyStat, ResearchMeta, ResearchSignal
from news_insight.sources.models import Source

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


def _signal_filters(
    window: Span, *, field: str | None, company: str | None, org: str | None
) -> list[ColumnElement[bool]]:
    rs = ResearchSignal
    where: list[ColumnElement[bool]] = [
        rs.lead.is_(True),
        rs.day >= window.start,
        rs.day <= window.end,
    ]
    if field is not None:
        where.append(rs.field == field)
    if company is not None:
        where.append(rs.company_keys.contains([company]))
    if org is not None:
        where.append(rs.orgs.contains([org]))
    return where


class ResearchDomain:
    name: Literal["research"] = "research"
    model = ResearchDailyStat
    region_dim: Literal["country"] = "country"
    has_orgs = True
    enrichment_regions = True

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
        """Papers (folded) with a watched company among their institutions."""
        if not watched:
            return 0
        rs = ResearchSignal
        return int(
            session.scalar(
                select(func.count()).where(
                    rs.lead,
                    rs.day >= window.start,
                    rs.day <= window.end,
                    rs.company_keys.overlap(watched),
                )
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
        recent: bool = False,
    ) -> tuple[int, list[Doc]]:
        rs = ResearchSignal
        where = _signal_filters(window, field=field, company=company, org=org)
        total = int(session.scalar(select(func.count()).select_from(rs).where(*where)) or 0)
        if total <= (page - 1) * size:
            return total, []
        order = (
            (rs.occurred_at.desc(), rs.item_id.desc())
            if recent
            else (rs.score.desc(), rs.occurred_at.desc(), rs.item_id.desc())
        )
        signals = session.scalars(
            select(rs).where(*where).order_by(*order).offset((page - 1) * size).limit(size)
        ).all()
        ids = [signal.item_id for signal in signals]
        details = {
            row.id: row
            for row in session.execute(
                select(
                    Item.id,
                    Item.url,
                    Item.title,
                    Source.name.label("source_name"),
                    ItemCard.title_ko,
                    ItemCard.summary_ko,
                    ResearchMeta.venue,
                    ResearchMeta.cited_by,
                )
                .join(Source, Source.id == Item.source_id)
                .outerjoin(
                    ItemCard,
                    and_(ItemCard.item_id == Item.id, ItemCard.status == CardStatus.READY),
                )
                .outerjoin(ResearchMeta, ResearchMeta.item_id == Item.id)
                .where(Item.id.in_(ids))
            )
        }
        refs = company_refs(session, sorted({k for s in signals for k in s.company_keys}))
        docs = []
        for signal in signals:
            row = details[signal.item_id]
            docs.append(
                Doc(
                    id=signal.item_id,
                    url=row.url,
                    title=row.title,
                    title_ko=row.title_ko,
                    summary=(row.summary_ko or [None])[0],
                    source_name=row.source_name,
                    occurred_at=signal.occurred_at,
                    field=signal.field,
                    field_label=field_label(signal.field),
                    companies=[refs[k] for k in signal.company_keys if k in refs],
                    watched=any(k in watched for k in signal.company_keys),
                    score=round(signal.score, 1),
                    venue=row.venue,
                    orgs=signal.orgs[:DOC_ORGS],
                    cited_by=row.cited_by,
                    cited_growth=signal.cited_growth,
                    mentions=signal.mentions,
                    upvotes=signal.upvotes or None,
                )
            )
        return total, docs
