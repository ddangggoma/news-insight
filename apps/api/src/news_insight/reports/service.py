"""Trend reports on request (plan 17 R1).

A signed-in reader asks for a report on a topic (with what they already know, a window and
optionally the dossier it grows from). The request waits in `trend_reports`; the host job
(`news-insight reports run`, launchd every minute, where the Claude CLI is logged in) takes
the oldest, has Claude plan the search, gathers the evidence, has Claude write the report,
checks every citation against the cards it was given and stores the HTML. Reports are shared
by the team like dossiers. A daily cap per reader and for the site keeps Claude usage bounded.
"""

import logging
from datetime import UTC, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from news_insight.auth.models import Role, User
from news_insight.digest.claude import ClaudeClient, ClaudeError
from news_insight.dossiers.models import Dossier
from news_insight.public.periods import KST
from news_insight.reports import evidence, prompts, render
from news_insight.reports.models import TrendReport

log = logging.getLogger(__name__)

WINDOWS = (30, 90, 180, 365)
STALE_AFTER = timedelta(minutes=45)  # a run longer than this died with its host job
MAX_ATTEMPTS = 2
ACTIVE = ("queued", "running")


class ReportError(ValueError):
    """A request the reader can fix (bad input)."""


class QuotaExceeded(Exception):
    """Too many reports today, or too many waiting."""


class ReportIn(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    brief: str | None = Field(default=None, max_length=4000)
    days: int = 90
    dossier_id: int | None = None

    @field_validator("topic")
    @classmethod
    def _topic(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("brief")
    @classmethod
    def _brief(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("days")
    @classmethod
    def _days(cls, value: int) -> int:
        if value not in WINDOWS:
            raise ValueError(f"days must be one of {WINDOWS}")
        return value


class ReportSummary(BaseModel):
    id: int
    topic: str
    title: str | None
    days: int
    status: str
    requested_by: str | None
    requested_at: datetime
    finished_at: datetime | None
    bottom_line: str | None
    error: str | None
    mine: bool
    position: int | None  # place in the queue while waiting


class ReportDetail(ReportSummary):
    brief: str | None
    dossier_id: int | None
    started_at: datetime | None
    model: str | None
    evidence: int
    stories: int
    can_retry: bool
    can_archive: bool


def _day_start(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(KST).date(), time(0, 0), tzinfo=KST)


def _count(session: Session, *conditions: Any) -> int:
    return session.scalar(select(func.count()).select_from(TrendReport).where(*conditions)) or 0


def request(
    session: Session,
    body: ReportIn,
    *,
    user: User,
    now: datetime,
    per_user_daily: int,
    site_daily: int,
) -> TrendReport:
    if body.dossier_id is not None:
        dossier = session.get(Dossier, body.dossier_id)
        if dossier is None or dossier.status != "active":
            raise ReportError("주제 파일을 찾을 수 없습니다.")
    today = TrendReport.requested_at >= _day_start(now)
    if user.role != Role.ADMIN:
        if (
            _count(session, TrendReport.requested_by == user.id, TrendReport.status.in_(ACTIVE))
            >= 2
        ):
            raise QuotaExceeded("작성 중인 보고서가 두 개 있습니다. 끝난 뒤에 요청하세요.")
        if _count(session, TrendReport.requested_by == user.id, today) >= per_user_daily:
            raise QuotaExceeded(f"보고서는 하루 {per_user_daily}건까지 요청할 수 있습니다.")
    if _count(session, today) >= site_daily:
        raise QuotaExceeded(f"오늘 사이트 전체 보고서 한도({site_daily}건)에 도달했습니다.")
    report = TrendReport(
        topic=body.topic,
        brief=body.brief,
        days=body.days,
        dossier_id=body.dossier_id,
        status="queued",
        requested_by=user.id,
        requested_at=now,
        attempts=0,
    )
    session.add(report)
    session.flush()
    return report


def _names(session: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(
        session.execute(select(User.id, User.name).where(User.id.in_(wanted))).tuples().all()
    )


def _queue(session: Session) -> dict[int, int]:
    waiting = session.scalars(
        select(TrendReport.id)
        .where(TrendReport.status.in_(ACTIVE))
        .order_by(TrendReport.status.desc(), TrendReport.requested_at)  # running first
    ).all()
    return {report_id: index + 1 for index, report_id in enumerate(waiting)}


def _summary(
    report: TrendReport, user: User, names: dict[int, str], queue: dict[int, int]
) -> dict[str, Any]:
    content = report.content or {}
    return {
        "id": report.id,
        "topic": report.topic,
        "title": content.get("title") or None,
        "days": report.days,
        "status": report.status,
        "requested_by": names.get(report.requested_by) if report.requested_by else None,
        "requested_at": report.requested_at,
        "finished_at": report.finished_at,
        "bottom_line": (content.get("bottom_line") or {}).get("judgement"),
        "error": report.error if report.status == "failed" else None,
        "mine": report.requested_by == user.id,
        "position": queue.get(report.id) if report.status == "queued" else None,
    }


def summaries(session: Session, *, user: User, limit: int = 100) -> list[ReportSummary]:
    reports = session.scalars(
        select(TrendReport)
        .where(TrendReport.status != "archived")
        .order_by(TrendReport.requested_at.desc())
        .limit(limit)
    ).all()
    names = _names(session, {r.requested_by for r in reports})
    queue = _queue(session)
    return [ReportSummary(**_summary(r, user, names, queue)) for r in reports]


def _may_change(report: TrendReport, user: User) -> bool:
    return user.role == Role.ADMIN or report.requested_by == user.id


def detail(session: Session, report: TrendReport, *, user: User) -> ReportDetail:
    names = _names(session, {report.requested_by})
    stats = report.stats or {}
    return ReportDetail(
        **_summary(report, user, names, _queue(session)),
        brief=report.brief,
        dossier_id=report.dossier_id,
        started_at=report.started_at,
        model=report.model,
        evidence=len(stats.get("sources") or {}),
        stories=int((stats.get("aggregates") or {}).get("stories") or 0),
        can_retry=report.status == "failed" and _may_change(report, user),
        can_archive=report.status not in ("running", "archived") and _may_change(report, user),
    )


def retry(report: TrendReport, *, user: User) -> None:
    if report.status != "failed" or not _may_change(report, user):
        raise ReportError("실패한 보고서만, 요청한 사람이나 관리자가 다시 요청할 수 있습니다.")
    report.status, report.error, report.attempts = "queued", None, 0


def archive(report: TrendReport, *, user: User) -> None:
    if report.status == "running" or not _may_change(report, user):
        raise ReportError("작성 중인 보고서는 보관할 수 없고, 요청한 사람이나 관리자만 보관합니다.")
    report.status = "archived"


# --- the host job -----------------------------------------------------------------------------


def requeue_stale(session: Session, *, now: datetime) -> int:
    """Runs whose host job died: try again, or give up after MAX_ATTEMPTS."""
    stale = TrendReport.status == "running", TrendReport.started_at < now - STALE_AFTER
    failed = session.execute(
        update(TrendReport)
        .where(*stale, TrendReport.attempts >= MAX_ATTEMPTS)
        .values(status="failed", error="작성이 시간 안에 끝나지 않았습니다.", finished_at=now)
    )
    again = session.execute(update(TrendReport).where(*stale).values(status="queued"))
    return int(getattr(failed, "rowcount", 0) or 0) + int(getattr(again, "rowcount", 0) or 0)


def claim(session: Session, *, now: datetime) -> TrendReport | None:
    report = session.scalars(
        select(TrendReport)
        .where(TrendReport.status == "queued")
        .order_by(TrendReport.requested_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if report is None:
        return None
    report.status, report.started_at = "running", now
    report.attempts += 1
    report.error = None
    session.flush()
    return report


def report_view(report: TrendReport) -> dict[str, Any]:
    """What the renderers need, from a stored report."""
    stats = report.stats or {}
    return {
        "topic": report.topic,
        "brief": report.brief,
        "period_from": stats.get("period_from", ""),
        "period_to": stats.get("period_to", ""),
        "corpus_since": stats.get("corpus_since"),
        "generated_at": report.finished_at.isoformat() if report.finished_at else None,
        "model": report.model,
        "content": report.content or {},
        "sources": stats.get("sources") or {},
        "stats": stats.get("aggregates") or {},
        "plan": report.plan or {},
    }


def _plan(client: ClaudeClient, report: TrendReport, *, model: str) -> tuple[evidence.Plan, float]:
    try:
        result = client.generate(
            {"topic": report.topic, "brief": report.brief or ""},
            schema=prompts.PLAN_SCHEMA,
            model=model,
            system=prompts.PLAN_SYSTEM,
            instruction=prompts.PLAN_INSTRUCTION,
        )
    except ClaudeError as error:
        log.warning("report plan failed, searching by the topic", extra={"error": str(error)})
        return evidence.default_plan(report.topic, report.brief), 0.0
    return evidence.plan_from(result.structured, topic=report.topic, brief=report.brief), (
        result.cost_usd
    )


def write(
    session: Session,
    report: TrendReport,
    *,
    client: ClaudeClient,
    model: str,
    embed: evidence.Embed | None,
    now: datetime,
) -> TrendReport:
    """Plan, gather, write, check and render one claimed report. Commits between the slow
    Claude calls so no transaction stays open for minutes."""
    plan, cost = _plan(client, report, model=model)
    report.plan = plan.as_dict()
    session.commit()
    dossier = session.get(Dossier, report.dossier_id) if report.dossier_id else None
    pack = evidence.gather(session, plan, days=report.days, now=now, embed=embed, dossier=dossier)
    if not pack.evidence:
        report.status, report.finished_at = "failed", datetime.now(UTC)
        report.error = (
            "근거 기간 안에서 이 주제의 카드를 찾지 못했습니다. 주제 표현이나 기간을 바꿔 보세요."
        )
        session.commit()
        return report
    sources = evidence.sources(pack)
    report.stats = {
        "period_from": pack.since.astimezone(KST).date().isoformat(),
        "period_to": pack.until.astimezone(KST).date().isoformat(),
        "corpus_since": pack.corpus_since.isoformat() if pack.corpus_since else None,
        "sources": sources,
        "aggregates": pack.stats,
        "unknown_companies": pack.unknown_companies,
    }
    session.commit()
    try:
        result = client.generate(
            evidence.payload(pack, topic=report.topic, brief=report.brief),
            schema=prompts.WRITE_SCHEMA,
            model=model,
            system=prompts.WRITE_SYSTEM,
            instruction=prompts.WRITE_INSTRUCTION,
        )
        content = render.validate(result.structured, (c.id for c in pack.evidence))
    except (ClaudeError, ValueError) as error:
        report.status, report.finished_at = "failed", datetime.now(UTC)
        report.error = f"보고서 작성 실패: {str(error)[:300]}"
        session.commit()
        return report
    report.content = content
    report.model = result.model
    report.cost_usd = round(cost + result.cost_usd, 4)
    report.finished_at = datetime.now(UTC)
    report.html = render.html(report_view(report))
    report.status = "ready"
    session.commit()
    return report


def run_next(
    session: Session,
    *,
    client: ClaudeClient,
    model: str,
    embed: evidence.Embed | None,
    now: datetime,
) -> TrendReport | None:
    """One report from the queue, if any."""
    requeue_stale(session, now=now)
    report = claim(session, now=now)
    session.commit()
    if report is None:
        return None
    report_id = report.id
    try:
        return write(session, report, client=client, model=model, embed=embed, now=now)
    except Exception as error:
        # a bug or a lost database must not leave the report running until it goes stale
        session.rollback()
        failed = session.get(TrendReport, report_id)
        if failed is not None:
            failed.status, failed.finished_at = "failed", datetime.now(UTC)
            failed.error = f"내부 오류: {type(error).__name__}"
            session.commit()
        raise
