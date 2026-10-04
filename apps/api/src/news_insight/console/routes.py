"""Operations console API. Reached only by the web server over the internal network (D16)."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from news_insight.collect.dead_letters import DeadLetterError, dismiss, retry
from news_insight.collect.models import DeadLetter, FetchOutcome
from news_insight.console import briefings as briefing_queries
from news_insight.console import cards as card_queries
from news_insight.console import queries
from news_insight.console import reviews as review_queries
from news_insight.console import stories as story_queries
from news_insight.console.auth import require_console_key
from news_insight.console.schemas import (
    CardFailure,
    CardStats,
    CardView,
    DeadLetterOut,
    ItemDetail,
    ItemRow,
    MoverOut,
    Overview,
    Page,
    PauseBody,
    Queued,
    RunOut,
    SourceDetail,
    SourceQualityRow,
    SourceRow,
    TopicCandidate,
)
from news_insight.db import get_db
from news_insight.digest import service as digest_service
from news_insight.digest.schemas import DigestOut, DigestSummary
from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from news_insight.sources.ladder import LadderError, pause_source, resume_source
from news_insight.sources.models import Source
from news_insight.sources.service import SourceNotFound, get_source

router = APIRouter(
    prefix="/api/admin", tags=["console"], dependencies=[Depends(require_console_key)]
)
DB = Annotated[Session, Depends(get_db)]
PageQ = Annotated[int, Query(ge=1)]
SizeQ = Annotated[int, Query(ge=1, le=100)]


def enqueue_collection(source_id: int) -> None:
    from news_insight.jobs.tasks import collect_source_task

    collect_source_task.delay(source_id)


def _source(session: Session, key: str) -> Source:
    try:
        return get_source(session, key)
    except SourceNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/overview")
def get_overview(session: DB) -> Overview:
    return queries.overview(session, now=datetime.now(UTC))


@router.get("/sources")
def list_sources(
    session: DB,
    track: Track | None = None,
    region: Region | None = None,
    stage: ValidationStage | None = None,
    source_status: Annotated[SourceStatus | None, Query(alias="status")] = None,
    q: str | None = None,
    page: PageQ = 1,
    size: SizeQ = 50,
) -> Page[SourceRow]:
    return queries.list_sources(
        session,
        track=track,
        region=region,
        stage=stage,
        status=source_status,
        q=q,
        page=page,
        size=size,
    )


@router.get("/sources/quality")
def sources_quality(
    session: DB,
    order: Literal["worst", "best"] = "worst",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[SourceQualityRow]:
    return queries.source_quality(session, now=datetime.now(UTC), order=order, limit=limit)


@router.get("/sources/{key}")
def get_source_detail(key: str, session: DB) -> SourceDetail:
    detail = queries.source_detail(session, key)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown source '{key}'")
    return detail


@router.post("/sources/{key}/pause")
def pause(key: str, body: PauseBody, session: DB) -> SourceRow:
    source = _source(session, key)
    try:
        pause_source(session, source, reason=body.reason)
    except LadderError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return queries.source_row(session, source)


@router.post("/sources/{key}/resume")
def resume(key: str, session: DB) -> SourceRow:
    source = _source(session, key)
    try:
        resume_source(session, source)
    except LadderError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return queries.source_row(session, source)


@router.post("/sources/{key}/collect")
def collect_now(key: str, session: DB) -> Queued:
    enqueue_collection(_source(session, key).id)
    return Queued(queued=True)


@router.get("/runs")
def list_runs(
    session: DB,
    outcome: FetchOutcome | None = None,
    source: str | None = None,
    page: PageQ = 1,
    size: SizeQ = 50,
) -> Page[RunOut]:
    return queries.list_runs(session, outcome=outcome, source_key=source, page=page, size=size)


@router.get("/dead-letters")
def list_dead_letters(
    session: DB,
    state: Literal["open", "resolved", "all"] = "open",
    page: PageQ = 1,
    size: SizeQ = 50,
) -> Page[DeadLetterOut]:
    return queries.list_dead_letters(session, state=state, page=page, size=size)


def _resolve(session: Session, dead_letter_id: int, action: str) -> DeadLetterOut:
    now = datetime.now(UTC)
    try:
        if action == "retry":
            retry(session, dead_letter_id, now=now)
        else:
            dismiss(session, dead_letter_id, now=now)
    except DeadLetterError as exc:
        code = (
            status.HTTP_404_NOT_FOUND if "does not exist" in str(exc) else status.HTTP_409_CONFLICT
        )
        raise HTTPException(code, str(exc)) from exc
    letter = session.get(DeadLetter, dead_letter_id)
    assert letter is not None
    return queries.dead_letter_out(session, letter)


@router.post("/dead-letters/{dead_letter_id}/retry")
def retry_dead_letter(dead_letter_id: int, session: DB) -> DeadLetterOut:
    return _resolve(session, dead_letter_id, "retry")


@router.post("/dead-letters/{dead_letter_id}/dismiss")
def dismiss_dead_letter(dead_letter_id: int, session: DB) -> DeadLetterOut:
    return _resolve(session, dead_letter_id, "dismiss")


@router.get("/items")
def list_items(
    session: DB,
    track: Track | None = None,
    source: str | None = None,
    q: str | None = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    page: PageQ = 1,
    size: SizeQ = 50,
) -> Page[ItemRow]:
    return queries.list_items(
        session,
        track=track,
        source_key=source,
        q=q,
        days=days,
        page=page,
        size=size,
        now=datetime.now(UTC),
    )


@router.get("/items/{item_id}")
def get_item(item_id: int, session: DB) -> ItemDetail:
    detail = queries.item_detail(session, item_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown item {item_id}")
    return detail


@router.get("/trends/movers")
def get_movers(
    session: DB,
    metric: str = "stars",
    days: Annotated[int, Query(ge=1, le=90)] = 1,
    track: Track | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[MoverOut]:
    return queries.movers(
        session, metric=metric, days=days, track=track, limit=limit, now=datetime.now(UTC)
    )


@router.get("/digests")
def list_digests(session: DB, page: PageQ = 1, size: SizeQ = 30) -> Page[DigestSummary]:
    return digest_service.list_digests(session, page=page, size=size)


@router.get("/digests/latest")
def latest_digest(session: DB) -> DigestOut:
    digest = digest_service.latest_digest(session)
    if digest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no digest yet")
    return digest_service.digest_out(session, digest)


@router.get("/digests/{digest_date}")
def get_digest(digest_date: date, session: DB) -> DigestOut:
    digest = digest_service.digest_for(session, digest_date)
    if digest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no digest for {digest_date}")
    return digest_service.digest_out(session, digest)


@router.get("/cards")
def list_cards(
    session: DB,
    track: Track | None = None,
    category: str | None = None,
    region: Region | None = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    q: str | None = None,
    field: str | None = None,
    business: str | None = None,
    impact: str | None = None,
    scope: str | None = None,
    dedup: bool = False,
    page: PageQ = 1,
    size: SizeQ = 60,
) -> Page[CardView]:
    return card_queries.list_cards(
        session,
        track=track,
        category=category,
        region=region,
        days=days,
        q=q,
        page=page,
        size=size,
        now=datetime.now(UTC),
        field=field,
        business=business,
        impact=impact,
        scope=scope,
        dedup=dedup,
    )


@router.get("/cards/failures")
def get_card_failures(
    session: DB, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[CardFailure]:
    return card_queries.card_failures(session, limit=limit)


@router.get("/topic-candidates")
def get_topic_candidates(
    session: DB,
    days: Annotated[int, Query(ge=1, le=180)] = 30,
    min_count: Annotated[int, Query(ge=1, le=100)] = 2,
) -> list[TopicCandidate]:
    from news_insight.console.topics import topic_candidates

    return topic_candidates(session, days=days, now=datetime.now(UTC), min_count=min_count)


@router.get("/cards/stats")
def get_card_stats(session: DB) -> CardStats:
    return card_queries.card_stats(session, now=datetime.now(UTC))


@router.get("/reviews/sample")
def review_sample(
    session: DB,
    seed: Annotated[str, Query(min_length=1, max_length=40)],
    size: Annotated[int, Query(ge=1, le=200)] = 30,
    track: Track | None = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
) -> review_queries.ReviewSample:
    return review_queries.sample(
        session, seed=seed, size=size, track=track, days=days, now=datetime.now(UTC)
    )


@router.post("/reviews")
def record_review(body: review_queries.ReviewBody, session: DB) -> review_queries.ReviewOut:
    try:
        return review_queries.record(session, body, now=datetime.now(UTC))
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/reviews/stats")
def review_stats(session: DB) -> review_queries.ReviewStats:
    return review_queries.stats(session)


@router.get("/reviews/export.csv")
def review_export(session: DB) -> Response:
    return Response(
        content=review_queries.export_csv(session),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="relevance-reviews.csv"'},
    )


@router.get("/stories")
def list_stories(
    session: DB,
    days: Annotated[int, Query(ge=1, le=30)] = 1,
    min_size: Annotated[int, Query(ge=1, le=100)] = 2,
    min_tracks: Annotated[int, Query(ge=1, le=4)] = 1,
    track: Track | None = None,
    business: str | None = None,
    page: PageQ = 1,
    size: SizeQ = 30,
) -> Page[story_queries.StoryView]:
    return story_queries.list_stories(
        session,
        days=days,
        min_size=min_size,
        min_tracks=min_tracks,
        track=track,
        business=business,
        page=page,
        size=size,
        now=datetime.now(UTC),
    )


@router.get("/signals")
def list_signals(
    session: DB,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[story_queries.SignalChain]:
    return story_queries.list_signals(session, days=days, now=datetime.now(UTC), limit=limit)


@router.get("/briefings")
def list_briefings(
    session: DB, limit: Annotated[int, Query(ge=1, le=100)] = 30
) -> list[briefing_queries.BriefingSummary]:
    return briefing_queries.summaries(session, limit=limit)


@router.get("/briefings/latest")
def latest_briefing(session: DB) -> briefing_queries.BriefingOut:
    briefing = briefing_queries.latest(session)
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no briefing yet")
    return briefing_queries.briefing_out(session, briefing)


@router.get("/briefings/{briefing_date}")
def get_briefing(briefing_date: date, session: DB) -> briefing_queries.BriefingOut:
    briefing = briefing_queries.for_date(session, briefing_date)
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no briefing for {briefing_date}")
    return briefing_queries.briefing_out(session, briefing)


class AlertOut(BaseModel):
    id: int
    key: str
    severity: str
    title: str
    detail: str
    opened_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    notified_at: datetime | None


@router.get("/alerts")
def list_alerts(session: DB, limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[AlertOut]:
    """Open alerts first, then the most recently resolved."""
    from sqlalchemy import select

    from news_insight.ops.models import OpsAlert

    rows = session.scalars(
        select(OpsAlert)
        .order_by(OpsAlert.resolved_at.is_not(None), OpsAlert.opened_at.desc())
        .limit(limit)
    )
    return [
        AlertOut(
            id=a.id,
            key=a.key,
            severity=a.severity.value,
            title=a.title,
            detail=a.detail,
            opened_at=a.opened_at,
            last_seen_at=a.last_seen_at,
            resolved_at=a.resolved_at,
            notified_at=a.notified_at,
        )
        for a in rows
    ]
