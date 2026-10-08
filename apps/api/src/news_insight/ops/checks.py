"""Operational health checks (requirements §10): publication SLA, collection, queues, cards.

Each check returns Findings for what is wrong right now; `ops.service` turns them into alert
episodes. Times are KST: freeze 04:40, publication 05:00 (launchd), grace until 05:20.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.auth.models import Role, User, UserStatus
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
CARD_FAILURE_RATE = 0.3
SLOW_WINDOW = timedelta(hours=1)
SLOW_LIMIT = 5  # responses over 5 s in the last hour


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
    if last is not None and last.ready + last.failed >= 20:
        rate = last.failed / (last.ready + last.failed)
        if rate >= CARD_FAILURE_RATE:
            findings.append(
                Finding(
                    "cards_failing",
                    Severity.WARNING,
                    f"마지막 카드 실행 실패율 {rate:.0%}",
                    f"성공 {last.ready} · 실패 {last.failed}. {(last.note or '')[:200]}",
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


def check_slow_requests(slow: list[str] | None) -> list[Finding]:
    """`slow` holds 'stamp path seconds' entries from the last hour (observability)."""
    if not slow or len(slow) < SLOW_LIMIT:
        return []
    paths: dict[str, int] = {}
    for entry in slow:
        parts = entry.split(" ")
        if len(parts) >= 2:
            paths[parts[1]] = paths.get(parts[1], 0) + 1
    top = ", ".join(f"{p} {n}회" for p, n in sorted(paths.items(), key=lambda kv: -kv[1])[:3])
    return [
        Finding(
            "api_slow",
            Severity.WARNING,
            f"최근 1시간 5초 이상 걸린 API 응답 {len(slow)}건",
            f"{top}. 캐시가 비어 있거나 집계가 무거운 경로입니다.",
        )
    ]


def check_accounts(session: Session) -> list[Finding]:
    """Plan 14: without an active admin nobody can approve sign-ups or open the console."""
    admins = session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.ADMIN, User.status == UserStatus.ACTIVE)
    )
    if admins:
        return []
    return [
        Finding(
            "no_admin",
            Severity.WARNING,
            "활성 관리자 계정이 없습니다",
            "가입 신청을 승인할 사람이 없습니다. 서버에서 "
            "`docker compose exec api news-insight users create-admin <아이디> --name <이름>`"
            "으로 만드세요.",
        )
    ]


HOST_SWAP_RATIO = 0.9
HOST_FREE_PCT = 10
ZERO_RUNS = 6  # an hour of card runs that made nothing


def check_host(host: dict[str, Any] | None) -> list[Finding]:
    """macOS memory from the host job's snapshot (ops/host.py); console only, never mailed."""
    from news_insight.ops.host import swap_ratio

    if not host or host.get("stale"):
        return []
    findings: list[Finding] = []
    ratio = swap_ratio(host)
    free = host.get("memory_free_pct")
    if (ratio is not None and ratio >= HOST_SWAP_RATIO) or (
        free is not None and free <= HOST_FREE_PCT
    ):
        findings.append(
            Finding(
                "host_memory",
                Severity.WARNING,
                "호스트 메모리가 부족합니다",
                f"스왑 {host.get('swap_used_mb')}/{host.get('swap_total_mb')} MB, "
                f"여유 메모리 {free}%. Docker가 다시 멈출 수 있습니다: "
                "Qwen 컨텍스트, 안 쓰는 앱, ARDAgent를 확인하세요.",
            )
        )
    qwen = host.get("qwen") or {}
    if qwen.get("state") not in (None, "loaded"):
        findings.append(
            Finding(
                "qwen_unloaded",
                Severity.INFO,
                f"로컬 Qwen 상태: {qwen.get('state')}",
                "카드 생성이 Qwen 없이 돌고 있습니다. LM Studio에서 모델을 불러오세요.",
            )
        )
    return findings


def check_card_output(session: Session) -> list[Finding]:
    """Runs keep happening but produce nothing (Qwen 400s, every metered engine at its reserve)."""
    from news_insight.ops.engines import card_engine_health

    health = card_engine_health(session)
    if health.zero_runs < ZERO_RUNS or pending_count(session) == 0:
        return []
    notes = "; ".join(e.latest_note for e in health.engines if e.latest_note)
    return [
        Finding(
            "cards_zero",
            Severity.WARNING,
            f"카드 생성이 최근 {health.zero_runs}회 연속 0건입니다",
            (notes or "실행은 되지만 결과가 없습니다.")[:400],
        )
    ]


def run_checks(
    session: Session,
    *,
    now: datetime,
    queue_length: int | None,
    slow_requests: list[str] | None = None,
    host: dict[str, Any] | None = None,
) -> list[Finding]:
    return [
        *check_host(host),
        *check_card_output(session),
        *check_publication(session, now=now),
        *check_collection(session, now=now),
        *check_queue(queue_length),
        *check_cards(session, now=now),
        *check_slow_requests(slow_requests),
        *check_accounts(session),
    ]
