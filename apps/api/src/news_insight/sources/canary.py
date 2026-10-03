"""V4 canary: judge 24 h of real collection runs before a source may enter quality trials."""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.sources.enums import SourceStatus, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import CheckResult, record_check
from news_insight.sources.models import Source, SourceValidationEvent

CANARY_WINDOW_HOURS = 24
MIN_RUNS = 4
MAX_ERROR_RATE = 0.10
MAX_RATE_LIMITED_RATE = 0.05
MAX_P95_LATENCY_MS = 10_000
MAX_DUPLICATE_RATE = 0.20
ERROR_OUTCOMES = frozenset({FetchOutcome.FAILED, FetchOutcome.DEAD_LETTERED})


@dataclass(frozen=True)
class CanaryMetrics:
    runs: int
    window_hours: float
    not_modified_rate: float
    rate_limited_rate: float
    error_rate: float
    latency_p95_ms: int
    duplicate_rate: float
    items_new: int


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(1, math.ceil(0.95 * len(ordered))) - 1]


def canary_metrics(runs: Sequence[FetchRun], *, now: datetime) -> CanaryMetrics:
    considered = [run for run in runs if run.outcome is not FetchOutcome.SKIPPED]
    total = len(considered)
    started = min((run.started_at for run in considered), default=now)
    items_new = sum(run.items_new for run in considered)
    return CanaryMetrics(
        runs=total,
        window_hours=round((now - started).total_seconds() / 3600, 2),
        not_modified_rate=_rate(
            sum(run.outcome is FetchOutcome.NOT_MODIFIED for run in considered), total
        ),
        rate_limited_rate=_rate(sum(run.http_status == 429 for run in considered), total),
        error_rate=_rate(sum(run.outcome in ERROR_OUTCOMES for run in considered), total),
        latency_p95_ms=_p95([run.elapsed_ms for run in considered if run.elapsed_ms is not None]),
        duplicate_rate=_rate(sum(run.duplicate_urls for run in considered), items_new),
        items_new=items_new,
    )


def evaluate_canary(runs: Sequence[FetchRun], *, now: datetime) -> CheckResult | None:
    metrics = canary_metrics(runs, now=now)
    if metrics.runs < MIN_RUNS or metrics.window_hours < CANARY_WINDOW_HOURS:
        return None
    reasons: list[str] = []
    if metrics.error_rate > MAX_ERROR_RATE:
        reasons.append(f"error rate {metrics.error_rate:.0%} exceeds {MAX_ERROR_RATE:.0%}")
    if metrics.rate_limited_rate > MAX_RATE_LIMITED_RATE:
        reasons.append(
            f"HTTP 429 rate {metrics.rate_limited_rate:.0%} exceeds {MAX_RATE_LIMITED_RATE:.0%}"
        )
    if metrics.latency_p95_ms > MAX_P95_LATENCY_MS:
        reasons.append(f"latency p95 {metrics.latency_p95_ms} ms exceeds {MAX_P95_LATENCY_MS} ms")
    if metrics.duplicate_rate > MAX_DUPLICATE_RATE:
        reasons.append(
            f"duplicate rate {metrics.duplicate_rate:.0%} exceeds {MAX_DUPLICATE_RATE:.0%}"
        )
    return CheckResult.from_reasons(reasons, asdict(metrics))


def observation_start(session: Session, source: Source) -> datetime | None:
    """The canary window restarts at the latest V3 pass or V4 failure."""
    event = SourceValidationEvent
    return session.scalar(
        select(func.max(event.created_at)).where(
            event.source_id == source.id,
            or_(
                and_(
                    event.stage == ValidationStage.V3,
                    event.outcome == ValidationOutcome.PASSED,
                ),
                and_(
                    event.stage == ValidationStage.V4,
                    event.outcome == ValidationOutcome.FAILED,
                ),
            ),
        )
    )


def run_canaries(session: Session, now: datetime) -> list[SourceValidationEvent]:
    candidates = session.scalars(
        select(Source)
        .where(
            Source.validation_stage == ValidationStage.V3,
            Source.status == SourceStatus.CANDIDATE,
        )
        .order_by(Source.key)
    )
    events: list[SourceValidationEvent] = []
    for source in list(candidates):
        since = observation_start(session, source)
        if since is None:
            continue
        runs = list(
            session.scalars(
                select(FetchRun)
                .where(FetchRun.source_id == source.id, FetchRun.started_at >= since)
                .order_by(FetchRun.started_at)
            )
        )
        result = evaluate_canary(runs, now=now)
        if result is not None:
            events.append(record_check(session, source, ValidationStage.V4, result))
    return events
