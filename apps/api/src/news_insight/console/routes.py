"""Operations console API. Reached only by the web server over the internal network (D16)."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from news_insight.collect.dead_letters import DeadLetterError, dismiss, retry
from news_insight.collect.models import DeadLetter, FetchOutcome
from news_insight.console import queries
from news_insight.console.auth import require_console_key
from news_insight.console.schemas import (
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
    SourceRow,
)
from news_insight.db import get_db
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
