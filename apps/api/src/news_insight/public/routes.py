"""Reader API for the public web. Reached only by the web server over the internal network."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from news_insight.console.schemas import Page
from news_insight.db import get_db
from news_insight.digest import service as digest_service
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestSummary
from news_insight.public import aggregates
from news_insight.public import feed as feed_queries
from news_insight.public import radar as radar_queries
from news_insight.public.auth import require_public_key
from news_insight.public.filters import FilterError, ReaderFilters
from news_insight.public.periods import (
    PeriodError,
    Window,
    calendar_window,
    current_key,
    rolling_window,
)
from news_insight.public.schemas import (
    CellDetail,
    FeedPage,
    Insights,
    PublicDigest,
    Radar,
    ReaderItemDetail,
    TaxonomyField,
    TaxonomyNode,
    TaxonomyOut,
)
from news_insight.taxonomy.catalog import (
    BUSINESS_KEYS,
    BUSINESSES,
    FIELD_KEYS,
    FIELDS,
    IMPACTS,
    SCOPES,
    TAXONOMY_REVISION,
    Node,
)

router = APIRouter(
    prefix="/api/public", tags=["public"], dependencies=[Depends(require_public_key)]
)
DB = Annotated[Session, Depends(get_db)]
Values = Annotated[list[str] | None, Query()]


def get_now() -> datetime:
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(get_now)]


def _unprocessable(error: ValueError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


def reader_filters(
    scope: str = "relevant",
    q: str | None = None,
    field: Values = None,
    theme: Values = None,
    business: Values = None,
    impact: Values = None,
    track: Values = None,
    region: Values = None,
) -> ReaderFilters:
    try:
        return ReaderFilters.build(
            scope=scope,
            q=q,
            field=field,
            theme=theme,
            business=business,
            impact=impact,
            track=track,
            region=region,
        )
    except FilterError as error:
        raise _unprocessable(error) from error


def feed_window(now: Now, period: str = "7d") -> Window:
    try:
        return rolling_window(period, now)
    except PeriodError as error:
        raise _unprocessable(error) from error


Filters = Annotated[ReaderFilters, Depends(reader_filters)]
FeedWindow = Annotated[Window, Depends(feed_window)]


def _nodes(values: Sequence[Node]) -> list[TaxonomyNode]:
    return [TaxonomyNode(key=node.key, label=node.name) for node in values]


@router.get("/taxonomy")
def get_taxonomy() -> TaxonomyOut:
    return TaxonomyOut(
        revision=TAXONOMY_REVISION,
        fields=[
            TaxonomyField(key=field.key, label=field.name, themes=_nodes(field.themes))
            for field in FIELDS
        ],
        businesses=_nodes(BUSINESSES),
        impacts=_nodes(IMPACTS),
        scopes=_nodes(SCOPES),
    )


@router.get("/items")
def list_items(
    session: DB,
    filters: Filters,
    window: FeedWindow,
    sort: Literal["recent", "relevance", "coverage"] = "recent",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 30,
) -> FeedPage:
    return feed_queries.feed(session, filters, window, sort=sort, page=page, size=size)


@router.get("/items/{item_id}")
def get_item(item_id: int, session: DB) -> ReaderItemDetail:
    detail = feed_queries.item_detail(session, item_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    return detail


@router.get("/facets")
def get_facets(session: DB, filters: Filters, window: FeedWindow) -> dict[str, dict[str, int]]:
    return aggregates.facets(session, filters, window)


@router.get("/insights")
def get_insights(session: DB, filters: Filters, window: FeedWindow) -> Insights:
    return aggregates.insights(session, filters, window)


def radar_window(now: Now, period: str = "week", key: str | None = None) -> Window:
    try:
        return calendar_window(period, key or current_key(period, now))
    except PeriodError as error:
        raise _unprocessable(error) from error


RadarPeriod = Annotated[Window, Depends(radar_window)]


@router.get("/radar")
def get_radar(session: DB, filters: Filters, window: RadarPeriod, now: Now) -> Radar:
    return radar_queries.radar(session, filters, window, current_key(window.kind, now))


@router.get("/radar/cell")
def get_radar_cell(
    session: DB, window: RadarPeriod, field: str, business: str, scope: str = "relevant"
) -> CellDetail:
    """One heatmap cell. The cell fixes field and business, so only the scope filter applies."""
    filters = reader_filters(scope=scope)
    if field not in FIELD_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown field '{field}'")
    if business != radar_queries.NO_BUSINESS and business not in BUSINESS_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown business '{business}'")
    return radar_queries.cell_detail(session, filters, window, field=field, business=business)


def _public_digest(session: Session, digest: Digest | None) -> PublicDigest:
    if digest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "digest not found")
    full = digest_service.digest_out(session, digest)
    return PublicDigest.model_validate(full.model_dump(exclude={"model", "cost_usd", "error"}))


@router.get("/digests")
def list_digests(
    session: DB,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 30,
) -> Page[DigestSummary]:
    return digest_service.list_digests(session, page=page, size=size)


@router.get("/digests/latest")
def latest_digest(session: DB) -> PublicDigest:
    return _public_digest(session, digest_service.latest_digest(session))


@router.get("/digests/{digest_date}")
def get_digest(digest_date: date, session: DB) -> PublicDigest:
    return _public_digest(session, digest_service.digest_for(session, digest_date))
