"""Read models for the console: every function returns response schemas, never ORM objects."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun
from news_insight.console.schemas import Health, Overview, RegionCount, StageCount, TrackCount
from news_insight.sources.enums import STAGE_ORDER, Region, SourceStatus, Track, ValidationStage
from news_insight.sources.models import Source
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
