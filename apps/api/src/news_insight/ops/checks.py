"""Operational health checks (requirements §10): publication SLA, collection, queues, cards.

Each check returns Findings for what is wrong right now; `ops.service` turns them into alert
episodes. Times are KST: freeze 04:40, publication 05:00 (launchd), grace until 05:20.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.briefing.service import failing
from news_insight.cards.models import CardRun
from news_insight.cards.service import pending_count
from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun
from news_insight.ops.models import Severity
from news_insight.strategy.models import StrategyRun, StrategyStatus

KST = ZoneInfo("Asia/Seoul")
FREEZE_DEADLINE = time(4, 55)
PUBLISH_DEADLINE = time(5, 20)
COLLECTION_WINDOW = timedelta(hours=1)
MIN_SUCCESS_RATE = 0.5
DLQ_LIMIT = 50
QUEUE_LIMIT = 500
CARD_STALL = timedelta(minutes=40)
CARD_BACKLOG = 5000


@dataclass(frozen=True)
class Finding:
    key: str
    severity: Severity
    title: str
    detail: str = ""


def check_publication(session: Session, *, now: datetime) -> list[Finding]:
    local = now.astimezone(KST)
    today = local.date()
    findings: list[Finding] = []
    if local.time() >= FREEZE_DEADLINE:
        frozen = session.scalar(
            select(func.count())
            .select_from(BriefingFreeze)
            .where(BriefingFreeze.briefing_date == today)
        )
        if not frozen:
            findings.append(
                Finding(
                    "freeze_missing",
                    Severity.CRITICAL,
                    f"{today} 후보 동결(04:40)이 없습니다",
                    "Celery beat·worker 상태를 확인하세요. 05:00 발행 작업이 대신 동결합니다.",
                )
            )
    if local.time() < PUBLISH_DEADLINE:
        return findings
    latest = session.scalars(
        select(Briefing)
        .where(Briefing.briefing_date == today)
        .order_by(Briefing.version.desc())
        .limit(1)
    ).first()
    if latest is None:
        findings.append(
            Finding(
                "publish_sla",
                Severity.CRITICAL,
                f"{today} 브리핑이 05:20까지 만들어지지 않았습니다",
                "launchd 다이제스트 작업(ops/logs/digest.log)과 Claude CLI 로그인을 확인하세요.",
            )
        )
    elif latest.status is BriefingStatus.BLOCKED:
        findings.append(
            Finding(
                "publish_blocked",
                Severity.WARNING,
                f"{today} 브리핑이 품질 게이트에서 차단되었습니다",
                "Fail-safe로 이전 정상본이 유지됩니다. 실패 게이트: "
                + ", ".join(failing(latest.gates)),
            )
        )
    if latest is not None and latest.strategy_id:
        run = session.get(StrategyRun, latest.strategy_id)
        if run is not None and run.status is StrategyStatus.FAILED:
            findings.append(
                Finding(
                    "strategy_failed",
                    Severity.WARNING,
                    f"{today} 페르소나·전략 생성 실패",
                    (run.error or "")[:300],
                )
            )
    return findings


def check_collection(session: Session, *, now: datetime) -> list[Finding]:
    since = now - COLLECTION_WINDOW
    counts = dict(
        session.execute(
            select(FetchRun.outcome, func.count())
            .where(FetchRun.started_at >= since)
            .group_by(FetchRun.outcome)
        )
        .tuples()
        .all()
    )
    ok = counts.get(FetchOutcome.SUCCESS, 0) + counts.get(FetchOutcome.NOT_MODIFIED, 0)
    bad = counts.get(FetchOutcome.FAILED, 0) + counts.get(FetchOutcome.DEAD_LETTERED, 0)
    findings: list[Finding] = []
    if ok == 0:
        findings.append(
            Finding(
                "collection_stalled",
                Severity.CRITICAL,
                "최근 1시간 동안 성공한 수집이 없습니다",
                f"실패 {bad}건. worker·scheduler 컨테이너와 네트워크를 확인하세요.",
            )
        )
    elif ok + bad >= 20 and ok / (ok + bad) < MIN_SUCCESS_RATE:
        findings.append(
            Finding(
                "collection_degraded",
                Severity.WARNING,
                f"최근 1시간 수집 성공률 {ok / (ok + bad):.0%}",
                f"성공 {ok} · 실패 {bad}",
            )
        )
    open_dlq = (
        session.scalar(
            select(func.count()).select_from(DeadLetter).where(DeadLetter.resolved_at.is_(None))
        )
        or 0
    )
    if open_dlq > DLQ_LIMIT:
        findings.append(
            Finding(
                "dlq_backlog",
                Severity.WARNING,
                f"처리 안 된 DLQ {open_dlq}건",
                "콘솔 → DLQ에서 재시도하거나 원인 소스를 일시정지하세요.",
            )
        )
    return findings


def check_queue(queue_length: int | None) -> list[Finding]:
    if queue_length is None:
        return [Finding("redis_unreachable", Severity.CRITICAL, "Redis에 연결할 수 없습니다")]
    if queue_length > QUEUE_LIMIT:
        return [
            Finding(
                "queue_backlog",
                Severity.WARNING,
                f"작업 큐 적체 {queue_length}건",
                "worker 동시성 또는 수집 주기를 확인하세요.",
            )
        ]
    return []


def check_cards(session: Session, *, now: datetime) -> list[Finding]:
    last = session.scalars(select(CardRun).order_by(CardRun.started_at.desc()).limit(1)).first()
    pending = pending_count(session)
    findings: list[Finding] = []
    if last is None or now - last.started_at > CARD_STALL:
        since = (
            "기록 없음" if last is None else last.started_at.astimezone(KST).strftime("%m-%d %H:%M")
        )
        if pending > 0:
            findings.append(
                Finding(
                    "cards_stalled",
                    Severity.WARNING,
                    "한국어 카드 생성이 40분 넘게 돌지 않았습니다",
                    f"마지막 실행 {since}, 대기 {pending}건. launchd(com.newsinsight.cards), "
                    "agy 로그인, LM Studio를 확인하세요.",
                )
            )
    if pending > CARD_BACKLOG:
        findings.append(
            Finding(
                "cards_backlog",
                Severity.INFO,
                f"카드 대기 {pending}건",
                "05:00 브리핑 후보는 카드가 있는 기사만 들어갑니다.",
            )
        )
    return findings


def run_checks(session: Session, *, now: datetime, queue_length: int | None) -> list[Finding]:
    return [
        *check_publication(session, now=now),
        *check_collection(session, now=now),
        *check_queue(queue_length),
        *check_cards(session, now=now),
    ]
