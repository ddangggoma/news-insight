"""The 특허 menu (plan 19 §1): patent documents by technology field, applicant company and
publishing office, from patent_meta (office publications and ip cards from the news).

Counts come from patent_daily_stats. The theme bars (the table has no theme column), the company
share, the watched-company count and the documents page are read live with the stats' document
conditions; patents are few (about a thousand a quarter), so these stay cheap. Documents are
ordered by the sources reporting them (their story), then by a watched applicant, then date.
Every response carries the coverage block: which sources the window's counts come from."""

from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, case, exists, false, func, literal, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.content.freshness import fresh_condition
from news_insight.content.models import Item, ItemDedup
from news_insight.patents.models import PatentDailyStat, PatentMeta, PatentSource
from news_insight.public.domains import (
    OTHER,
    Coverage,
    Doc,
    Span,
    company_refs,
    field_label,
    instants,
)
from news_insight.public.periods import KST
from news_insight.sources.models import Source
from news_insight.stories.models import Story, StoryItem
from news_insight.taxonomy.catalog import FIELD_KEYS

WATCHED_BONUS = 0.5  # orders a watched applicant after the next higher press count
OFFICE_LABELS = {
    "EP": "유럽(EPO)",
    "US": "미국",
    "CN": "중국",
    "WO": "국제(PCT)",
    "KR": "한국",
    "JP": "일본",
    "DE": "독일",
    "GB": "영국",
    "FR": "프랑스",
    "TW": "대만",
}
NOTE_PILOT = "지식재산 뉴스·EPO 공보 파일럿 기준(공보 수집은 EPO OPS 키 등록 후)"
NOTE_OPS = "지식재산 뉴스·EPO 공보(OPS) 기준"


def _window(window: Span) -> list[ColumnElement[bool]]:
    start, end = instants(window)
    return [
        Item.canary.is_(False),
        ~exists().where(ItemDedup.item_id == Item.id, ItemDedup.duplicate_of.is_not(None)),
        fresh_condition(),
        Item.occurred_at >= start,
        Item.occurred_at < end,
    ]


def _meta_field(field: str) -> ColumnElement[bool]:
    if field == OTHER:
        return PatentMeta.field.not_in(sorted(FIELD_KEYS))
    return PatentMeta.field == field


def _ready_card() -> ColumnElement[bool]:
    return and_(ItemCard.item_id == Item.id, ItemCard.status == CardStatus.READY)


class PatentDomain:
    name: Literal["patent"] = "patent"
    model = PatentDailyStat
    region_dim: Literal["office"] = "office"
    has_orgs = False

    def region_column(self) -> Any:
        return PatentDailyStat.office

    def region_label(self, key: str) -> str:
        return OFFICE_LABELS.get(key, key)

    def coverage(self, session: Session, window: Span) -> Coverage:
        stat = PatentDailyStat
        counts = dict(
            session.execute(
                select(stat.source, func.sum(stat.n))
                .where(stat.dim == "total", stat.day >= window.start, stat.day <= window.end)
                .group_by(stat.source)
            )
            .tuples()
            .all()
        )
        ops = int(counts.get(PatentSource.OPS.value, 0))
        return Coverage(
            news=int(counts.get(PatentSource.NEWS.value, 0)),
            eps=int(counts.get(PatentSource.EPS.value, 0)),
            ops=ops,
            note=NOTE_OPS if ops else NOTE_PILOT,
        )

    def company_share(self, session: Session, window: Span, total: int) -> tuple[float | None, int]:
        with_company = func.count().filter(func.cardinality(PatentMeta.company_keys) > 0)
        docs, companies = session.execute(
            select(func.count(), with_company)
            .select_from(PatentMeta)
            .join(Item, Item.id == PatentMeta.item_id)
            .where(*_window(window))
        ).one()
        return (round(companies / docs, 3) if docs else None), int(companies)

    def watched_count(self, session: Session, window: Span, watched: list[str]) -> int:
        if not watched:
            return 0
        return int(
            session.scalar(
                select(func.count())
                .select_from(PatentMeta)
                .join(Item, Item.id == PatentMeta.item_id)
                .where(PatentMeta.company_keys.overlap(watched), *_window(window))
            )
            or 0
        )

    def themes(self, session: Session, field: str, windows: list[Span]) -> dict[str, list[int]]:
        """Card themes of the field's patents, per window (live: the stats have no themes)."""
        whole = Span(start=windows[0].start, end=windows[-1].end)
        rows = session.execute(
            select(Item.occurred_at, ItemCard.themes)
            .select_from(PatentMeta)
            .join(Item, Item.id == PatentMeta.item_id)
            .join(ItemCard, _ready_card())
            .where(_meta_field(field), *_window(whole))
        ).all()
        prefix = f"{field}__"
        out: dict[str, list[int]] = defaultdict(lambda: [0] * len(windows))
        for occurred_at, themes in rows:
            day = _kst_day(occurred_at)
            index = next((i for i, w in enumerate(windows) if w.start <= day <= w.end), None)
            if index is None:
                continue
            for theme in set(themes or []):
                if str(theme).startswith(prefix):
                    out[str(theme)][index] += 1
        return dict(out)

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
            conditions.append(_meta_field(field))
        if company is not None:
            conditions.append(PatentMeta.company_keys.contains([company]))
        total = int(
            session.scalar(
                select(func.count())
                .select_from(PatentMeta)
                .join(Item, Item.id == PatentMeta.item_id)
                .where(*conditions)
            )
            or 0
        )
        if total <= (page - 1) * size:
            return total, []
        press = func.coalesce(Story.source_count, 0)
        is_watched = PatentMeta.company_keys.overlap(watched) if watched else false()
        score = (press + case((is_watched, WATCHED_BONUS), else_=literal(0.0))).label("score")
        rows = session.execute(
            select(
                Item.id,
                Item.url,
                Item.title,
                Item.occurred_at,
                Source.name.label("source_name"),
                ItemCard.title_ko,
                ItemCard.summary_ko,
                PatentMeta.field,
                PatentMeta.publication_number,
                PatentMeta.office,
                PatentMeta.source,
                PatentMeta.applicants,
                PatentMeta.company_keys,
                press.label("press"),
                score,
            )
            .select_from(PatentMeta)
            .join(Item, Item.id == PatentMeta.item_id)
            .join(Source, Source.id == Item.source_id)
            .outerjoin(ItemCard, _ready_card())
            .outerjoin(StoryItem, StoryItem.item_id == Item.id)
            .outerjoin(Story, Story.id == StoryItem.story_id)
            .where(*conditions)
            .order_by(score.desc(), Item.occurred_at.desc(), Item.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        refs = company_refs(session, sorted({k for row in rows for k in row.company_keys or []}))
        docs = []
        for row in rows:
            doc_field = row.field if row.field in FIELD_KEYS else OTHER
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
                    companies=[refs[k] for k in row.company_keys or [] if k in refs],
                    watched=any(k in watched for k in row.company_keys or []),
                    score=round(float(row.score), 1),
                    publication_number=row.publication_number,
                    office=row.office,
                    patent_source=str(row.source),
                    applicants=list(row.applicants or []),
                    press=int(row.press),
                )
            )
        return total, docs


def _kst_day(moment: datetime) -> Any:
    return moment.astimezone(KST).date()
