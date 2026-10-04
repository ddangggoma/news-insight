"""Public read models built on the console queries, restricted to published content."""

from datetime import date, datetime, timedelta

from sqlalchemy import Text, func, literal_column, or_, select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingStatus
from news_insight.briefing.service import current_briefing
from news_insight.cards.models import CardStatus, ItemCard
from news_insight.console.briefings import briefing_out
from news_insight.console.cards import list_cards
from news_insight.console.schemas import CardView
from news_insight.content.models import Item
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestItemRef
from news_insight.reader.schemas import (
    ArchiveEntry,
    ReaderBriefing,
    ReaderCard,
    ReaderPage,
    ReaderPersona,
    ReaderSection,
    ReaderStrategy,
    TaxonomyCounts,
)

TRACK_ORDER = ("news", "research_ip", "oss", "community")
COUNT_WINDOW_DAYS = 30


def reader_card(view: CardView) -> ReaderCard:
    item, card = view.item, view.card
    return ReaderCard(
        id=item.id,
        title=item.title,
        title_ko=card.title_ko,
        summary_ko=card.summary_ko,
        keywords=card.keywords,
        url=item.url,
        source_name=item.source_name,
        track=item.track.value,
        category=item.category,
        region=item.region.value,
        published_at=item.published_at,
        first_seen_at=item.first_seen_at,
        field=card.field,
        themes=card.themes,
        businesses=card.businesses,
        impact=card.impact,
        relevance=card.relevance,
        coverage=view.story.source_count if view.story else None,
    )


def published(session: Session, briefing_date: date | None = None) -> Briefing | None:
    """The current briefing, or the latest published version for a date."""
    if briefing_date is None:
        return current_briefing(session)
    return session.scalars(
        select(Briefing)
        .where(Briefing.briefing_date == briefing_date, Briefing.status == BriefingStatus.PUBLISHED)
        .order_by(Briefing.version.desc())
        .limit(1)
    ).first()


def _neighbour(session: Session, day: date, *, later: bool) -> date | None:
    column = Briefing.briefing_date
    return session.scalar(
        select(func.min(column) if later else func.max(column)).where(
            Briefing.status == BriefingStatus.PUBLISHED, column > day if later else column < day
        )
    )


def reader_briefing(session: Session, briefing: Briefing) -> ReaderBriefing:
    full = briefing_out(session, briefing)
    digest = full.digest
    summaries = {t.track.value: t.summary for t in digest.content.tracks} if digest else {}
    by_track = {s.track: s.items for s in full.sections}
    sections = [
        ReaderSection(
            track=track,
            summary=summaries.get(track),
            items=[reader_card(view) for view in by_track[track]],
        )
        for track in (*TRACK_ORDER, *(t for t in by_track if t not in TRACK_ORDER))
        if track in by_track
    ]
    refs: dict[int, DigestItemRef] = {}
    strategy = None
    if full.strategy is not None:
        run = full.strategy
        strategy = ReaderStrategy(
            personas=[ReaderPersona.model_validate(p.model_dump()) for p in run.personas],
            report=run.report,
            review_verdict=str(run.review.get("verdict")) if run.review else None,
            dropped_claims=run.dropped_claims,
        )
        refs.update({ref.id: ref for ref in run.items})
    if digest is not None:
        refs.update({ref.id: ref for ref in digest.items})
    blocking = [gate for gate in full.gates if gate.blocking]
    return ReaderBriefing(
        briefing_date=full.briefing_date,
        version=full.version,
        published_at=full.published_at,
        headline=digest.content.headline if digest else None,
        overview=digest.content.overview if digest else None,
        insights=digest.content.insights if digest else [],
        sections=sections,
        strategy=strategy,
        refs=list(refs.values()),
        gates_passed=sum(1 for gate in blocking if gate.passed),
        gates_total=len(blocking),
        previous_date=_neighbour(session, briefing.briefing_date, later=False),
        next_date=_neighbour(session, briefing.briefing_date, later=True),
    )


def archive(session: Session, *, page: int, size: int) -> tuple[list[ArchiveEntry], int]:
    latest = (
        select(Briefing.briefing_date, func.max(Briefing.version).label("version"))
        .where(Briefing.status == BriefingStatus.PUBLISHED)
        .group_by(Briefing.briefing_date)
        .subquery()
    )
    total = session.scalar(select(func.count()).select_from(latest)) or 0
    rows = session.execute(
        select(Briefing, Digest.content["headline"].astext)
        .join(
            latest,
            (latest.c.briefing_date == Briefing.briefing_date)
            & (latest.c.version == Briefing.version),
        )
        .outerjoin(Digest, Digest.id == Briefing.digest_id)
        .order_by(Briefing.briefing_date.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).tuples()
    entries = [
        ArchiveEntry(
            briefing_date=briefing.briefing_date,
            version=briefing.version,
            headline=headline,
            items=len(briefing.shortlist),
            published_at=briefing.published_at,
        )
        for briefing, headline in rows
    ]
    return entries, total


def search_cards(
    session: Session,
    *,
    q: str | None,
    field: str | None,
    theme: str | None,
    business: str | None,
    impact: str | None,
    track: str | None,
    days: int | None,
    page: int,
    size: int,
    now: datetime,
) -> ReaderPage:
    from news_insight.sources.enums import Track

    result = list_cards(
        session,
        track=Track(track) if track in {t.value for t in Track} else None,
        category=None,
        region=None,
        days=days,
        q=q,
        page=page,
        size=size,
        now=now,
        field=field,
        theme=theme,
        business=business,
        impact=impact,
        scope="visible",
        dedup=True,
    )
    return ReaderPage(
        items=[reader_card(view) for view in result.items],
        total=result.total,
        page=result.page,
        size=result.size,
    )


def taxonomy_counts(session: Session, *, now: datetime) -> TaxonomyCounts:
    since = now - timedelta(days=COUNT_WINDOW_DAYS)
    visible = [
        ItemCard.status == CardStatus.READY,
        or_(ItemCard.scope.is_(None), ItemCard.scope != "irrelevant"),
        Item.first_seen_at >= since,
    ]
    base = select(ItemCard).join(Item, Item.id == ItemCard.item_id).where(*visible)

    def grouped(column: object) -> dict[str, int]:
        rows = session.execute(
            select(column, func.count())  # type: ignore[call-overload]
            .select_from(ItemCard)
            .join(Item, Item.id == ItemCard.item_id)
            .where(*visible, column.is_not(None))  # type: ignore[attr-defined]
            .group_by(column)
        ).tuples()
        return {str(key): int(count) for key, count in rows}

    def exploded(column: object) -> dict[str, int]:
        element = func.jsonb_array_elements_text(column).table_valued("value").alias("e")
        value = literal_column("e.value", Text)
        rows = session.execute(
            select(value, func.count())
            .select_from(ItemCard)
            .join(Item, Item.id == ItemCard.item_id)
            .join(element, literal_column("true"))
            .where(*visible)
            .group_by(value)
        ).tuples()
        return {str(key): int(count) for key, count in rows}

    return TaxonomyCounts(
        window_days=COUNT_WINDOW_DAYS,
        total=session.scalar(select(func.count()).select_from(base.subquery())) or 0,
        fields=grouped(ItemCard.field),
        themes=exploded(ItemCard.themes),
        businesses=exploded(ItemCard.businesses),
        impacts=grouped(ItemCard.impact),
    )
