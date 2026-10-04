"""Read models for the console: every function returns response schemas, never ORM objects."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.console.schemas import (
    CardBody,
    DeadLetterOut,
    Health,
    ItemDetail,
    ItemRow,
    MetricPoint,
    MoverOut,
    Overview,
    Page,
    RegionCount,
    RevisionOut,
    RunOut,
    SourceDetail,
    SourceRow,
    StageCount,
    TrackCount,
    ValidationEventOut,
)
from news_insight.content.models import Item, ItemMetricSnapshot, ItemRevision
from news_insight.content.trends import metric_movers
from news_insight.sources.enums import (
    STAGE_ORDER,
    Region,
    SourceStatus,
    Track,
    ValidationStage,
)
from news_insight.sources.models import Source, SourceValidationEvent
from news_insight.sources.portfolio import TRACK_TARGETS, region_capacity

HEALTH_WINDOW = timedelta(hours=24)


def overview(session: Session, *, now: datetime) -> Overview:
    rows = (
        session.execute(select(Source.track, Source.region, Source.validation_stage, Source.status))
        .tuples()
        .all()
    )

    def active(stage: ValidationStage, status: SourceStatus) -> bool:
        return status is SourceStatus.ACTIVE and stage is ValidationStage.V6

    tracks = [
        TrackCount(
            track=track,
            total=sum(1 for row in rows if row[0] is track),
            active=sum(1 for row in rows if row[0] is track and active(row[2], row[3])),
            target=TRACK_TARGETS[track],
        )
        for track in Track
    ]
    regions = [
        RegionCount(
            region=region,
            total=sum(1 for row in rows if row[1] is region),
            active=sum(1 for row in rows if row[1] is region and active(row[2], row[3])),
            capacity=region_capacity(region),
        )
        for region in Region
    ]
    stages = [
        StageCount(stage=stage, count=sum(1 for row in rows if row[2] is stage))
        for stage in STAGE_ORDER
    ]
    since = now - HEALTH_WINDOW
    outcomes = dict(
        session.execute(
            select(FetchRun.outcome, func.count())
            .where(FetchRun.started_at >= since)
            .group_by(FetchRun.outcome)
        )
        .tuples()
        .all()
    )
    items_new = session.scalar(
        select(func.coalesce(func.sum(FetchRun.items_new), 0)).where(FetchRun.started_at >= since)
    )
    health = Health(
        window_hours=int(HEALTH_WINDOW.total_seconds() // 3600),
        runs=sum(outcomes.values()),
        success=outcomes.get(FetchOutcome.SUCCESS, 0),
        not_modified=outcomes.get(FetchOutcome.NOT_MODIFIED, 0),
        failed=outcomes.get(FetchOutcome.FAILED, 0),
        dead_lettered=outcomes.get(FetchOutcome.DEAD_LETTERED, 0),
        skipped=outcomes.get(FetchOutcome.SKIPPED, 0),
        items_new=int(items_new or 0),
        paused_sources=sum(1 for row in rows if row[3] is SourceStatus.PAUSED),
        open_dead_letters=session.scalar(
            select(func.count()).select_from(DeadLetter).where(DeadLetter.resolved_at.is_(None))
        )
        or 0,
    )
    return Overview(generated_at=now, tracks=tracks, regions=regions, stages=stages, health=health)


def _offset(page: int, size: int) -> int:
    return (page - 1) * size


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _source_row(source: Source, runtime: SourceRuntime | None, items_total: int) -> SourceRow:
    return SourceRow(
        key=source.key,
        name=source.name,
        track=source.track,
        category=source.category,
        region=source.region,
        access_method=source.access_method,
        validation_stage=source.validation_stage,
        status=source.status,
        paused_reason=source.paused_reason,
        next_due_at=runtime.next_due_at if runtime else None,
        interval_seconds=runtime.interval_seconds if runtime else None,
        consecutive_failures=runtime.consecutive_failures if runtime else 0,
        last_success_at=runtime.last_success_at if runtime else None,
        items_total=items_total,
    )


def source_row(session: Session, source: Source) -> SourceRow:
    runtime = session.get(SourceRuntime, source.id)
    total = session.scalar(
        select(func.count()).select_from(Item).where(Item.source_id == source.id)
    )
    return _source_row(source, runtime, total or 0)


def list_sources(
    session: Session,
    *,
    track: Track | None,
    region: Region | None,
    stage: ValidationStage | None,
    status: SourceStatus | None,
    q: str | None,
    page: int,
    size: int,
) -> Page[SourceRow]:
    conditions = []
    if track is not None:
        conditions.append(Source.track == track)
    if region is not None:
        conditions.append(Source.region == region)
    if stage is not None:
        conditions.append(Source.validation_stage == stage)
    if status is not None:
        conditions.append(Source.status == status)
    if q:
        pattern = _like(q)
        conditions.append(
            Source.key.ilike(pattern, escape="\\") | Source.name.ilike(pattern, escape="\\")
        )
    counts = select(Item.source_id, func.count().label("n")).group_by(Item.source_id).subquery()
    statement = (
        select(Source, SourceRuntime, func.coalesce(counts.c.n, 0))
        .outerjoin(SourceRuntime, SourceRuntime.source_id == Source.id)
        .outerjoin(counts, counts.c.source_id == Source.id)
        .where(*conditions)
        .order_by(Source.track, Source.key)
        .offset(_offset(page, size))
        .limit(size)
    )
    total = session.scalar(select(func.count()).select_from(Source).where(*conditions)) or 0
    rows = [
        _source_row(source, runtime, int(n))
        for source, runtime, n in session.execute(statement).tuples()
    ]
    return Page[SourceRow](items=rows, total=total, page=page, size=size)


def _run_out(run: FetchRun, source_key: str) -> RunOut:
    return RunOut(
        id=run.id,
        source_key=source_key,
        started_at=run.started_at,
        outcome=run.outcome,
        http_status=run.http_status,
        elapsed_ms=run.elapsed_ms,
        items_new=run.items_new,
        items_updated=run.items_updated,
        items_unchanged=run.items_unchanged,
        error_code=run.error_code,
        error_message=run.error_message,
        canary=run.canary,
    )


def latest_metrics(session: Session, item_ids: list[int]) -> dict[int, dict[str, int]]:
    if not item_ids:
        return {}
    snapshots = session.scalars(
        select(ItemMetricSnapshot)
        .where(ItemMetricSnapshot.item_id.in_(item_ids))
        .order_by(ItemMetricSnapshot.item_id, ItemMetricSnapshot.captured_at.desc())
        .distinct(ItemMetricSnapshot.item_id)
    )
    return {snapshot.item_id: dict(snapshot.metrics) for snapshot in snapshots}


def korean_titles(session: Session, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    rows = session.execute(
        select(ItemCard.item_id, ItemCard.title_ko).where(
            ItemCard.item_id.in_(item_ids), ItemCard.status == CardStatus.READY
        )
    ).tuples()
    return {item_id: title for item_id, title in rows if title}


def card_body(card: ItemCard) -> CardBody:
    return CardBody(
        title_ko=card.title_ko,
        summary_ko=list(card.summary_ko),
        keywords=list(card.keywords),
        status=card.status.value,
        engine=card.engine,
        model=card.model,
        generated_at=card.generated_at,
        field=card.field,
        themes=list(card.themes or []),
        businesses=list(card.businesses or []),
        impact=card.impact,
        scope=card.scope,
        relevance=card.relevance,
    )


def item_rows(session: Session, pairs: list[tuple[Item, Source]]) -> list[ItemRow]:
    ids = [item.id for item, _ in pairs]
    metrics = latest_metrics(session, ids)
    titles = korean_titles(session, ids)
    return [
        ItemRow(
            id=item.id,
            title=item.title,
            url=item.url,
            source_key=source.key,
            source_name=source.name,
            track=item.track,
            category=source.category,
            region=source.region,
            published_at=item.published_at,
            first_seen_at=item.first_seen_at,
            revision=item.revision,
            canary=item.canary,
            metrics=metrics.get(item.id, {}),
            title_ko=titles.get(item.id),
        )
        for item, source in pairs
    ]


def source_detail(session: Session, key: str) -> SourceDetail | None:
    source = session.scalars(select(Source).where(Source.key == key)).one_or_none()
    if source is None:
        return None
    events = session.scalars(
        select(SourceValidationEvent)
        .where(SourceValidationEvent.source_id == source.id)
        .order_by(SourceValidationEvent.id.desc())
        .limit(50)
    )
    runs = session.scalars(
        select(FetchRun)
        .where(FetchRun.source_id == source.id)
        .order_by(FetchRun.started_at.desc())
        .limit(20)
    )
    items = session.scalars(
        select(Item)
        .where(Item.source_id == source.id)
        .order_by(Item.first_seen_at.desc(), Item.published_at.desc().nulls_last(), Item.id.desc())
        .limit(20)
    )
    return SourceDetail(
        source=source_row(session, source),
        endpoint_url=source.endpoint_url,
        official_domain=source.official_domain,
        operator=source.operator,
        language=source.language,
        poll_class=source.poll_class,
        dx_relevance=source.dx_relevance,
        terms_url=source.terms_url,
        storage_right=source.storage_right,
        config=dict(source.config),
        events=[
            ValidationEventOut(
                stage=event.stage,
                outcome=event.outcome,
                reasons=list(event.reasons),
                created_at=event.created_at,
            )
            for event in events
        ],
        runs=[_run_out(run, source.key) for run in runs],
        items=item_rows(session, [(item, source) for item in items]),
    )


def list_runs(
    session: Session,
    *,
    outcome: FetchOutcome | None,
    source_key: str | None,
    page: int,
    size: int,
) -> Page[RunOut]:
    conditions = []
    if outcome is not None:
        conditions.append(FetchRun.outcome == outcome)
    if source_key:
        conditions.append(Source.key == source_key)
    base = (
        select(FetchRun, Source.key)
        .join(Source, Source.id == FetchRun.source_id)
        .where(*conditions)
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(
        base.order_by(FetchRun.started_at.desc(), FetchRun.id.desc())
        .offset(_offset(page, size))
        .limit(size)
    ).tuples()
    return Page[RunOut](
        items=[_run_out(run, key) for run, key in rows], total=total, page=page, size=size
    )


def dead_letter_out(session: Session, letter: DeadLetter) -> DeadLetterOut:
    source = session.get(Source, letter.source_id)
    return DeadLetterOut(
        id=letter.id,
        source_key=source.key if source else f"source#{letter.source_id}",
        error_code=letter.error_code,
        error_message=letter.error_message,
        attempts=letter.attempts,
        created_at=letter.created_at,
        resolved_at=letter.resolved_at,
        resolution=letter.resolution,
    )


def list_dead_letters(session: Session, *, state: str, page: int, size: int) -> Page[DeadLetterOut]:
    conditions = []
    if state == "open":
        conditions.append(DeadLetter.resolved_at.is_(None))
    elif state == "resolved":
        conditions.append(DeadLetter.resolved_at.is_not(None))
    total = session.scalar(select(func.count()).select_from(DeadLetter).where(*conditions)) or 0
    letters = session.scalars(
        select(DeadLetter)
        .where(*conditions)
        .order_by(DeadLetter.id.desc())
        .offset(_offset(page, size))
        .limit(size)
    )
    return Page[DeadLetterOut](
        items=[dead_letter_out(session, letter) for letter in letters],
        total=total,
        page=page,
        size=size,
    )


def list_items(
    session: Session,
    *,
    track: Track | None,
    source_key: str | None,
    q: str | None,
    days: int | None,
    page: int,
    size: int,
    now: datetime,
) -> Page[ItemRow]:
    conditions = []
    if track is not None:
        conditions.append(Item.track == track)
    if source_key:
        conditions.append(Source.key == source_key)
    if q:
        conditions.append(Item.title.ilike(_like(q), escape="\\"))
    if days:
        conditions.append(Item.first_seen_at >= now - timedelta(days=days))
    base = select(Item, Source).join(Source, Source.id == Item.source_id).where(*conditions)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    pairs = list(
        session.execute(
            base.order_by(
                Item.first_seen_at.desc(), Item.published_at.desc().nulls_last(), Item.id.desc()
            )
            .offset(_offset(page, size))
            .limit(size)
        ).tuples()
    )
    return Page[ItemRow](items=item_rows(session, pairs), total=total, page=page, size=size)


def item_detail(session: Session, item_id: int) -> ItemDetail | None:
    pair = (
        session.execute(
            select(Item, Source).join(Source, Source.id == Item.source_id).where(Item.id == item_id)
        )
        .tuples()
        .one_or_none()
    )
    if pair is None:
        return None
    item, source = pair
    revisions = session.scalars(
        select(ItemRevision).where(ItemRevision.item_id == item.id).order_by(ItemRevision.revision)
    )
    snapshots = session.scalars(
        select(ItemMetricSnapshot)
        .where(ItemMetricSnapshot.item_id == item.id)
        .order_by(ItemMetricSnapshot.captured_at)
    )
    card = session.scalars(select(ItemCard).where(ItemCard.item_id == item.id)).one_or_none()
    return ItemDetail(
        item=item_rows(session, [(item, source)])[0],
        summary=item.summary,
        body=item.body,
        author=item.author,
        revisions=[
            RevisionOut(revision=rev.revision, title=rev.title, recorded_at=rev.recorded_at)
            for rev in revisions
        ],
        metric_history=[
            MetricPoint(captured_at=snap.captured_at, metrics=dict(snap.metrics))
            for snap in snapshots
        ],
        card=card_body(card) if card is not None else None,
    )


def movers(
    session: Session,
    *,
    metric: str,
    days: int,
    track: Track | None,
    limit: int,
    now: datetime,
) -> list[MoverOut]:
    found = metric_movers(
        session, metric=metric, window=timedelta(days=days), now=now, track=track, limit=limit
    )
    sources = {
        source.id: source
        for source in session.scalars(
            select(Source).where(Source.id.in_({mover.item.source_id for mover in found}))
        )
    }
    rows = item_rows(session, [(mover.item, sources[mover.item.source_id]) for mover in found])
    return [
        MoverOut(item=row, current=mover.current, baseline=mover.baseline, delta=mover.delta)
        for row, mover in zip(rows, found, strict=True)
    ]
