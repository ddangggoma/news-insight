"""Public reader API (§9): read-only, no login. Caddy exposes /api/public to everyone."""

from datetime import UTC, date, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from news_insight.config import Settings, get_settings
from news_insight.db import get_db
from news_insight.reader import feed, queries
from news_insight.reader.schemas import ArchivePage, ReaderBriefing, ReaderPage, TaxonomyCounts
from news_insight.taxonomy.catalog import LABELS

router = APIRouter(prefix="/api/public", tags=["reader"])
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
Text = Annotated[str | None, Query(max_length=100)]
CACHE = "public, max-age=60"


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/briefings/latest")
def latest_briefing(db: DB, response: Response) -> ReaderBriefing | None:
    briefing = queries.published(db)
    response.headers["Cache-Control"] = CACHE
    return queries.reader_briefing(db, briefing) if briefing is not None else None


@router.get("/briefings/{briefing_date}")
def briefing_on(briefing_date: date, db: DB, response: Response) -> ReaderBriefing:
    briefing = queries.published(db, briefing_date)
    if briefing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no published briefing on that date")
    response.headers["Cache-Control"] = CACHE
    return queries.reader_briefing(db, briefing)


@router.get("/archive")
def archive(
    db: DB,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ArchivePage:
    entries, total = queries.archive(db, page=page, size=size)
    response.headers["Cache-Control"] = CACHE
    return ArchivePage(items=entries, total=total, page=page, size=size)


@router.get("/cards")
def cards(
    db: DB,
    response: Response,
    q: Text = None,
    field: Text = None,
    theme: Text = None,
    business: Text = None,
    impact: Text = None,
    track: Text = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    size: Annotated[int, Query(ge=1, le=60)] = 30,
) -> ReaderPage:
    response.headers["Cache-Control"] = CACHE
    return queries.search_cards(
        db,
        q=(q or "").strip() or None,
        field=field,
        theme=theme,
        business=business,
        impact=impact,
        track=track,
        days=days,
        page=page,
        size=size,
        now=_now(),
    )


@router.get("/taxonomy")
def taxonomy(db: DB, response: Response) -> TaxonomyCounts:
    response.headers["Cache-Control"] = "public, max-age=300"
    return queries.taxonomy_counts(db, now=_now())


@router.get("/feed.xml")
def rss(
    db: DB,
    settings: Config,
    field: Text = None,
    theme: Text = None,
    business: Text = None,
    impact: Text = None,
) -> Response:
    base = settings.public_base_url
    node = theme or field or business or impact
    if node is None:
        entries, _ = queries.archive(db, page=1, size=30)
        body = feed.briefings_feed(entries, base_url=base)
    else:
        page = queries.search_cards(
            db,
            q=None,
            field=field,
            theme=theme,
            business=business,
            impact=impact,
            track=None,
            days=7,
            page=1,
            size=50,
            now=_now(),
        )
        filters = {"field": field, "theme": theme, "business": business, "impact": impact}
        params = urlencode({name: value for name, value in filters.items() if value})
        body = feed.cards_feed(
            page.items,
            base_url=base,
            label=LABELS.get(node, node),
            link=f"{base.rstrip('/')}/topics?{params}",
        )
    return Response(
        body,
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )
