"""Reader API for the public web. Reached only by the web server over the internal network."""

import threading
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from news_insight.ask import service as ask_service
from news_insight.console.schemas import Page
from news_insight.db import get_db
from news_insight.digest import service as digest_service
from news_insight.digest.models import Digest
from news_insight.digest.schemas import DigestSummary
from news_insight.periodic import service as periodic_service
from news_insight.public import aggregates, radar_cache
from news_insight.public import briefings as briefing_queries
from news_insight.public import companies as company_queries
from news_insight.public import feed as feed_queries
from news_insight.public import patents as patent_queries
from news_insight.public import periodic as periodic_queries
from news_insight.public import radar as radar_queries
from news_insight.public.auth import require_public_key
from news_insight.public.distribution import Distribution, DistributionError, distribution
from news_insight.public.filters import FilterError, ReaderFilters
from news_insight.public.periods import (
    PeriodError,
    Window,
    calendar_window,
    current_key,
    rolling_window,
)
from news_insight.public.schemas import (
    CompanyRadar,
    FeedPage,
    Insights,
    PublicDigest,
    Radar,
    ReaderItemDetail,
    TaxonomyField,
    TaxonomyNode,
    TaxonomyOut,
    TopicDetail,
)
from news_insight.taxonomy.catalog import (
    FIELD_KEYS,
    FIELDS,
    IMPACTS,
    SCOPES,
    SIGNAL_TYPES,
    TAXONOMY_REVISION,
    THEME_KEYS,
    Node,
)
from news_insight.taxonomy.views import TaxonomyOut as SchemesOut
from news_insight.taxonomy.views import taxonomy_view

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
    signal: Values = None,
    impact: Values = None,
    track: Values = None,
    region: Values = None,
    company: Values = None,
    node: Values = None,
) -> ReaderFilters:
    try:
        return ReaderFilters.build(
            scope=scope,
            q=q,
            field=field,
            theme=theme,
            signal=signal,
            impact=impact,
            track=track,
            region=region,
            company=company,
            node=node,
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
        signal_types=_nodes(SIGNAL_TYPES),
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
RadarCache = Annotated[object | None, Depends(radar_cache.cache_client)]


@router.get("/radar", response_model=Radar)
def get_radar(
    session: DB, filters: Filters, window: RadarPeriod, now: Now, cache: RadarCache
) -> Response:
    body, hit = radar_cache.cached_json(
        radar_cache.view_key("radar", window, filters),
        radar_cache.ttl_for(window, now),
        lambda: radar_queries.radar(session, filters, window, current_key(window.kind, now), now),
        client=cache,
    )
    return Response(
        body, media_type="application/json", headers={"X-Cache": "hit" if hit else "miss"}
    )


@router.get("/radar/distribution", response_model=Distribution)
def get_radar_distribution(
    session: DB,
    filters: Filters,
    window: RadarPeriod,
    now: Now,
    cache: RadarCache,
    scheme: Annotated[str, Query(min_length=1, max_length=40)] = "technology",
    depth: Annotated[int, Query(ge=1, le=10)] = 1,
    root: Annotated[str | None, Query(max_length=121)] = None,
) -> Response:
    """Cards by node at any depth of any scheme, under an optional base node (plan 15-4b)."""

    def build() -> Distribution:
        try:
            return distribution(session, filters, window, scheme=scheme, depth=depth, root=root)
        except DistributionError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    body, hit = radar_cache.cached_json(
        radar_cache.view_key(f"distribution:{scheme}:{depth}:{root or ''}", window, filters),
        radar_cache.ttl_for(window, now),
        build,
        client=cache,
    )
    return Response(
        body, media_type="application/json", headers={"X-Cache": "hit" if hit else "miss"}
    )


@router.get("/radar/companies", response_model=CompanyRadar)
def get_radar_companies(
    session: DB, filters: Filters, window: RadarPeriod, now: Now, cache: RadarCache
) -> Response:
    """Company radar (plan 12): momentum, activity shifts, theme leaders, entrants, pairs."""
    body, hit = radar_cache.cached_json(
        radar_cache.view_key("companies", window, filters),
        radar_cache.ttl_for(window, now),
        lambda: company_queries.company_radar(
            session, filters, window, current_key(window.kind, now), now
        ),
        client=cache,
    )
    return Response(
        body, media_type="application/json", headers={"X-Cache": "hit" if hit else "miss"}
    )


@router.get("/radar/topic", response_model=TopicDetail)
def get_radar_topic(
    session: DB,
    filters: Filters,
    window: RadarPeriod,
    now: Now,
    cache: RadarCache,
    kind: Literal["field", "theme", "keyword", "company"],
    value: Annotated[str, Query(min_length=1, max_length=200)],
) -> Response:
    """One field, theme, keyword or company (normalized key) over the radar window and filters."""
    if kind == "field" and value not in FIELD_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown field '{value}'")
    if kind == "theme" and value not in THEME_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown theme '{value}'")
    body, hit = radar_cache.cached_json(
        radar_cache.view_key("topic", window, filters, {"kind": kind, "value": value}),
        radar_cache.ttl_for(window, now),
        lambda: radar_queries.topic_detail(
            session, filters, window, kind=kind, value=value, now=now
        ),
        client=cache,
    )
    return Response(
        body, media_type="application/json", headers={"X-Cache": "hit" if hit else "miss"}
    )


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


@router.get("/briefings")
def list_briefings(
    session: DB,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Page[briefing_queries.BriefingEntry]:
    entries, total = briefing_queries.archive(session, page=page, size=size)
    return Page[briefing_queries.BriefingEntry](items=entries, total=total, page=page, size=size)


@router.get("/briefings/latest")
def latest_briefing(session: DB) -> briefing_queries.PublicBriefing:
    briefing = briefing_queries.published(session)
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no published briefing yet")
    return briefing_queries.public_briefing(session, briefing)


@router.get("/briefings/{briefing_date}")
def get_briefing(briefing_date: date, session: DB) -> briefing_queries.PublicBriefing:
    briefing = briefing_queries.published(session, briefing_date)
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no published briefing on that date")
    return briefing_queries.public_briefing(session, briefing)


@router.get("/periodic")
def list_periodic(session: DB) -> list[periodic_queries.PeriodicEntry]:
    return periodic_queries.recent(session)


@router.get("/periodic/{kind}/latest")
def latest_periodic(kind: str, session: DB) -> periodic_queries.PublicPeriodic:
    row = periodic_service.latest(session, kind)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no published {kind} briefing yet")
    return periodic_queries.public_periodic(session, row)


@router.get("/periodic/{kind}/{key}")
def get_periodic(kind: str, key: str, session: DB) -> periodic_queries.PublicPeriodic:
    row = periodic_service.published(session, kind, key) if kind in periodic_service.KINDS else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no published {kind} briefing for {key}")
    return periodic_queries.public_periodic(session, row)


@router.get("/taxonomy/schemes")
def get_taxonomy_schemes(session: DB) -> SchemesOut:
    """Schemes and their active node trees of any depth (plan 15)."""
    return taxonomy_view(session)


@router.get("/patents")
def get_patents(
    session: DB,
    now: Now,
    kind: Literal["month", "quarter"] = "month",
    page: Annotated[int, Query(ge=1, le=100)] = 1,
) -> patent_queries.PatentView:
    """Patent signals by period, technology area and company (plan 16 #5)."""
    return patent_queries.patent_view(session, kind=kind, now=now, page=page)


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    days: int = Field(default=30, ge=1, le=365)
    node: str | None = Field(default=None, max_length=120)


def ask_engines() -> tuple[ask_service.Embed, ask_service.Chat, str]:
    from news_insight.config import get_settings
    from news_insight.taxonomy.embeddings import embedder

    settings = get_settings()
    chat = ask_service.lm_studio_chat(settings.lm_studio_url, settings.lm_studio_model)
    return embedder(), chat, settings.lm_studio_model


Engines = Annotated[tuple[ask_service.Embed, ask_service.Chat, str], Depends(ask_engines)]
# one question at a time per API process: the local Qwen also writes the cards
_asking = threading.Lock()


@router.post("/ask")
def post_ask(session: DB, body: AskIn, now: Now, engines: Engines) -> ask_service.AskResult:
    """Answer a question from the cards, citing them (plan 16 #1)."""
    if not _asking.acquire(blocking=False):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "another question is running")
    embed, chat, model = engines
    try:
        return ask_service.ask(
            session,
            body.question.strip(),
            days=body.days,
            node=body.node,
            embed=embed,
            chat=chat,
            model=model,
            now=now,
        )
    except Exception as exc:  # noqa: BLE001 - LM Studio down, a timeout, a missing model
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"local model unavailable: {type(exc).__name__}"
        ) from exc
    finally:
        _asking.release()


@router.get("/version")
def schema_version(request: Request) -> dict[str, str]:
    """Hash of the public API's OpenAPI shape. The web server keys its cache on it, so a
    deploy that changes a response never renders new pages from old cached JSON (PERF-3)."""
    import hashlib
    import json

    cached = getattr(request.app.state, "public_schema_version", None)
    if cached is None:
        spec = request.app.openapi()
        public = {
            path: op for path, op in spec.get("paths", {}).items() if path.startswith("/api/public")
        }
        body = json.dumps(
            {"paths": public, "components": spec.get("components", {})}, sort_keys=True
        )
        cached = hashlib.sha256(body.encode()).hexdigest()[:12]
        request.app.state.public_schema_version = cached
    return {"schema": cached}
