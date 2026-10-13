"""Trend report API (plan 17 R1), under the reader key with the reader's session token, like
dossiers. The web asks here; the host job writes the report."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from news_insight.config import Settings, get_settings
from news_insight.db import get_db
from news_insight.dossiers.routes import Reader
from news_insight.export.document import download
from news_insight.public.auth import require_public_key
from news_insight.public.routes import Now
from news_insight.reports import render, service
from news_insight.reports.models import TrendReport

router = APIRouter(
    prefix="/api/public/reports", tags=["reports"], dependencies=[Depends(require_public_key)]
)
DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]

# The report page is our own HTML but carries model-written text and outside links: no scripts,
# no outside resources, links leave in a new tab. The web frame adds its own sandbox.
REPORT_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none';"
    " form-action 'none'; frame-ancestors 'self'"
)


def _report(db: Session, report_id: int) -> TrendReport:
    report = db.get(TrendReport, report_id)
    if report is None or report.status == "archived":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such report")
    return report


def _ready(db: Session, report_id: int) -> TrendReport:
    report = _report(db, report_id)
    if report.status != "ready" or not report.html:
        raise HTTPException(status.HTTP_409_CONFLICT, "the report is not written yet")
    return report


@router.get("")
def list_reports(db: DB, user: Reader) -> list[service.ReportSummary]:
    return service.summaries(db, user=user)


@router.post("", status_code=status.HTTP_201_CREATED)
def request_report(
    db: DB, user: Reader, now: Now, settings: Config, body: service.ReportIn
) -> service.ReportDetail:
    try:
        report = service.request(
            db,
            body,
            user=user,
            now=now,
            per_user_daily=settings.report_user_daily,
            site_daily=settings.report_site_daily,
        )
    except service.QuotaExceeded as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from None
    except service.ReportError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    db.commit()
    return service.detail(db, report, user=user)


@router.get("/{report_id}")
def get_report(report_id: int, db: DB, user: Reader) -> service.ReportDetail:
    return service.detail(db, _report(db, report_id), user=user)


@router.get("/{report_id}/html", response_class=HTMLResponse)
def report_html(report_id: int, db: DB, user: Reader) -> HTMLResponse:
    report = _ready(db, report_id)
    return HTMLResponse(
        report.html or "",
        headers={
            "Content-Security-Policy": REPORT_CSP,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{report_id}/export")
def export_report(
    report_id: int,
    db: DB,
    user: Reader,
    format: Annotated[str, Query(pattern="^(md|docx|pptx|html)$")] = "md",
) -> Response:
    report = _ready(db, report_id)
    stem = f"동향보고서-{report.id}-{report.topic[:40]}"
    if format == "html":
        from urllib.parse import quote

        return Response(
            report.html or "",
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="report-{report.id}.html";'
                f" filename*=UTF-8''{quote(stem)}.html"
            },
        )
    return download(render.document(service.report_view(report)), format, stem)


@router.post("/{report_id}/retry")
def retry_report(report_id: int, db: DB, user: Reader) -> service.ReportDetail:
    report = _report(db, report_id)
    try:
        service.retry(report, user=user)
    except service.ReportError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
    return service.detail(db, report, user=user)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_report(report_id: int, db: DB, user: Reader) -> None:
    report = _report(db, report_id)
    try:
        service.archive(report, user=user)
    except service.ReportError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None
    db.commit()
