"""Reader views of the weekly and monthly briefings (plan 13 C4)."""

from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.digest.schemas import DigestItemRef
from news_insight.periodic import service
from news_insight.periodic.models import PeriodicBriefing
from news_insight.periodic.schemas import PeriodicContent, referenced_ids
from news_insight.public.periods import calendar_window
from news_insight.sources.models import Source


class PeriodicEntry(BaseModel):
    kind: str
    key: str
    label: str
    headline: str
    period_start: date
    period_end: date  # inclusive


class DailyEntry(BaseModel):
    briefing_date: date
    headline: str | None


class PublicPeriodic(PeriodicEntry):
    version: int
    days: int
    generated_at: datetime
    content: PeriodicContent
    refs: list[DigestItemRef]
    daily: list[DailyEntry]
    previous_key: str | None
    next_key: str | None


def entry(row: PeriodicBriefing) -> PeriodicEntry:
    return PeriodicEntry(
        kind=row.kind,
        key=row.period_key,
        label=f"{service.LABEL[row.kind]} 브리핑",
        headline=str(row.content.get("headline", "")),
        period_start=row.period_start,
        period_end=row.period_end - timedelta(days=1),
    )


def recent(session: Session, *, limit: int = 12) -> list[PeriodicEntry]:
    return [entry(row) for row in service.recent(session, limit=limit)]


def public_periodic(session: Session, row: PeriodicBriefing) -> PublicPeriodic:
    content = PeriodicContent.model_validate(row.content)
    ids = referenced_ids(content)
    refs = (
        [
            DigestItemRef(
                id=item.id,
                title=item.title,
                url=item.url,
                source_name=source.name,
                track=item.track,
            )
            for item, source in session.execute(
                select(Item, Source)
                .join(Source, Source.id == Item.source_id)
                .where(Item.id.in_(ids))
            ).tuples()
        ]
        if ids
        else []
    )
    window = calendar_window(row.kind, row.period_key)
    daily = [
        DailyEntry(
            briefing_date=briefing.briefing_date, headline=(digest.content or {}).get("headline")
        )
        for briefing, digest in service.daily_briefings(session, window)
    ]
    neighbours = {
        "previous": window.previous().key,
        "next": window.next_key,
    }
    return PublicPeriodic(
        **entry(row).model_dump(),
        version=row.version,
        days=row.days,
        generated_at=row.generated_at,
        content=content,
        refs=sorted(refs, key=lambda ref: ref.id),
        daily=daily,
        previous_key=neighbours["previous"]
        if service.published(session, row.kind, neighbours["previous"])
        else None,
        next_key=neighbours["next"]
        if service.published(session, row.kind, neighbours["next"])
        else None,
    )
