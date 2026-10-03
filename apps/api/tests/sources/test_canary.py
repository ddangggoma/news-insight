from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.sources.canary import canary_metrics, evaluate_canary, run_canaries
from news_insight.sources.enums import STAGE_ORDER, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import CheckResult, record_check
from news_insight.sources.models import Source
from tests.factories import build_source

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def run(
    hours_ago: float,
    *,
    outcome: FetchOutcome = FetchOutcome.SUCCESS,
    status: int | None = 200,
    elapsed: int | None = 300,
    new: int = 5,
    duplicates: int = 0,
    source_id: int = 1,
) -> FetchRun:
    return FetchRun(
        source_id=source_id,
        started_at=NOW - timedelta(hours=hours_ago),
        outcome=outcome,
        http_status=status,
        elapsed_ms=elapsed,
        items_new=new,
        duplicate_urls=duplicates,
    )


def healthy(hours: float = 30, count: int = 6, source_id: int = 1) -> list[FetchRun]:
    step = hours / (count - 1)
    return [run(hours - n * step, source_id=source_id) for n in range(count)]


def test_metrics_summarise_runs() -> None:
    runs = [
        run(30, elapsed=100, new=4, duplicates=1),
        run(20, outcome=FetchOutcome.NOT_MODIFIED, status=304, elapsed=200, new=0),
        run(10, outcome=FetchOutcome.FAILED, status=429, elapsed=None, new=0),
        run(1, elapsed=4000, new=4, duplicates=1),
    ]

    metrics = canary_metrics(runs, now=NOW)

    assert (metrics.runs, metrics.window_hours) == (4, 30.0)
    assert (metrics.not_modified_rate, metrics.rate_limited_rate, metrics.error_rate) == (
        0.25,
        0.25,
        0.25,
    )
    assert (metrics.latency_p95_ms, metrics.duplicate_rate, metrics.items_new) == (4000, 0.25, 8)


def test_not_ready_before_24_hours() -> None:
    assert evaluate_canary(healthy(hours=20), now=NOW) is None


def test_not_ready_with_too_few_runs() -> None:
    assert evaluate_canary(healthy(hours=30, count=3), now=NOW) is None


def test_healthy_canary_passes_with_metrics() -> None:
    result = evaluate_canary(healthy(), now=NOW)

    assert result is not None and result.passed
    assert result.metrics["runs"] == 6


def test_unhealthy_canary_lists_every_reason() -> None:
    runs = healthy()[:4] + [
        run(2, outcome=FetchOutcome.FAILED, status=429, elapsed=None),
        run(1, elapsed=12_000, new=5, duplicates=5),
    ]

    result = evaluate_canary(runs, now=NOW)

    assert result is not None and not result.passed
    assert any("error rate" in reason for reason in result.reasons)
    assert any("429" in reason for reason in result.reasons)
    assert any("p95" in reason for reason in result.reasons)


def test_skipped_runs_are_ignored() -> None:
    runs = healthy() + [run(0.5, outcome=FetchOutcome.SKIPPED, status=None, elapsed=None)]

    assert canary_metrics(runs, now=NOW).runs == 6


def at_v3(session: Session, *, passed_hours_ago: float) -> Source:
    source = build_source()
    session.add(source)
    session.flush()
    for stage in STAGE_ORDER[1 : STAGE_ORDER.index(ValidationStage.V3) + 1]:
        record_check(session, source, stage, CheckResult(passed=True))
    for event in source.validation_events:
        event.created_at = NOW - timedelta(hours=passed_hours_ago)
    session.flush()
    return source


@pytest.mark.db
def test_run_canaries_promotes_ready_candidates(db_session: Session) -> None:
    source = at_v3(db_session, passed_hours_ago=30)
    stale_failure = run(40, outcome=FetchOutcome.FAILED, status=503, source_id=source.id)
    db_session.add_all([stale_failure, *healthy(hours=29, source_id=source.id)])
    db_session.flush()

    events = run_canaries(db_session, NOW)

    assert [(event.stage, event.outcome) for event in events] == [
        (ValidationStage.V4, ValidationOutcome.PASSED)
    ]
    assert source.validation_stage is ValidationStage.V4


@pytest.mark.db
def test_failed_canary_restarts_the_window(db_session: Session) -> None:
    source = at_v3(db_session, passed_hours_ago=30)
    failure = record_check(
        db_session, source, ValidationStage.V4, CheckResult.from_reasons(["error rate 50%"])
    )
    failure.created_at = NOW - timedelta(hours=2)
    db_session.add_all(healthy(hours=29, source_id=source.id))
    db_session.flush()

    assert run_canaries(db_session, NOW) == []
    assert source.validation_stage is ValidationStage.V3
