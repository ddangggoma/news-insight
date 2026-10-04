from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.collect.contracts import CollectContext, CollectorError, CollectResult, RawItem
from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.collect.service import collect_source
from news_insight.content.models import Item, ItemRevision
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import SourceStatus, ValidationStage
from news_insight.sources.models import Source
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


class StubCollector:
    def __init__(self, *outcomes: CollectResult | CollectorError) -> None:
        self._outcomes = list(outcomes)
        self.contexts: list[CollectContext] = []

    def collect(self, context: CollectContext) -> CollectResult:
        self.contexts.append(context)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, CollectorError):
            raise outcome
        return outcome


class Budget:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[tuple[str, int | None]] = []

    def try_acquire(self, domain: str, *, per_minute: int | None = None) -> bool:
        self.calls.append((domain, per_minute))
        return self.allow


def raw(n: int) -> RawItem:
    return RawItem(stable_id=f"id-{n}", url=f"https://www.example.com/{n}", title=f"Title {n}")


def ok(*items: RawItem, etag: str | None = None) -> CollectResult:
    return CollectResult(items=list(items), status_code=200, elapsed_ms=120, etag=etag)


NOT_MODIFIED = CollectResult(items=[], status_code=304, elapsed_ms=40, not_modified=True)


def transient() -> CollectorError:
    return CollectorError("timeout", "timed out", retryable=True)


@pytest.fixture
def fetcher() -> Iterator[SafeFetcher]:
    with SafeFetcher() as instance:
        yield instance


def collectable(session: Session, **overrides: Any) -> Source:
    source = build_source(**{"validation_stage": ValidationStage.V3, **overrides})
    session.add(source)
    session.flush()
    return source


def collect(
    session: Session,
    source: Source,
    stub: StubCollector,
    fetcher: SafeFetcher,
    *,
    budget: Budget | None = None,
    now: datetime = NOW,
) -> FetchRun:
    return collect_source(
        session,
        source,
        fetcher=fetcher,
        limiter=budget or Budget(),
        now=now,
        collector_factory=lambda method, _fetcher: stub,
    )


def runtime_of(session: Session, source: Source) -> SourceRuntime:
    runtime = session.get(SourceRuntime, source.id)
    assert runtime is not None
    return runtime


def count(session: Session, model: type[Any]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_success_stores_items_and_schedules_the_next_poll(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)

    run = collect(db_session, source, StubCollector(ok(raw(1), raw(2))), fetcher)

    runtime = runtime_of(db_session, source)
    assert (run.outcome, run.http_status, run.items_new, run.canary) == (
        FetchOutcome.SUCCESS,
        200,
        2,
        True,
    )
    assert run.finished_at == NOW + timedelta(milliseconds=120)
    assert (runtime.interval_seconds, runtime.next_due_at) == (900, NOW + timedelta(seconds=900))
    assert runtime.lease_until is None
    assert count(db_session, Item) == 2


def test_identical_recollection_writes_nothing_and_backs_off(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    stub = StubCollector(ok(raw(1)), ok(raw(1)))
    collect(db_session, source, stub, fetcher)

    run = collect(db_session, source, stub, fetcher, now=NOW + timedelta(minutes=15))

    runtime = runtime_of(db_session, source)
    assert (run.items_new, run.items_unchanged) == (0, 1)
    assert (runtime.interval_seconds, runtime.consecutive_idle) == (1350, 1)
    assert count(db_session, ItemRevision) == 1


def test_not_modified_reuses_validators_and_backs_off(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    stub = StubCollector(ok(raw(1), etag='"v1"'), NOT_MODIFIED)
    collect(db_session, source, stub, fetcher)

    run = collect(db_session, source, stub, fetcher, now=NOW + timedelta(minutes=15))

    assert stub.contexts[1].etag == '"v1"'
    assert run.outcome is FetchOutcome.NOT_MODIFIED
    assert runtime_of(db_session, source).etag == '"v1"'
    assert runtime_of(db_session, source).interval_seconds == 1350


def test_transient_failure_schedules_a_backoff_retry(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)

    run = collect(db_session, source, StubCollector(transient()), fetcher)

    runtime = runtime_of(db_session, source)
    assert (run.outcome, run.attempt, run.error_code) == (FetchOutcome.FAILED, 1, "timeout")
    assert (runtime.consecutive_failures, runtime.next_due_at) == (
        1,
        NOW + timedelta(seconds=60),
    )
    assert count(db_session, DeadLetter) == 0


def test_fourth_consecutive_failure_is_dead_lettered(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    stub = StubCollector(transient(), transient(), transient(), transient())
    now = NOW
    delays = []
    for _ in range(3):
        collect(db_session, source, stub, fetcher, now=now)
        due = runtime_of(db_session, source).next_due_at
        delays.append(int((due - now).total_seconds()))
        now = due

    run = collect(db_session, source, stub, fetcher, now=now)

    letter = db_session.scalars(select(DeadLetter)).one()
    runtime = runtime_of(db_session, source)
    assert delays == [60, 120, 240]
    assert (run.outcome, run.attempt) == (FetchOutcome.DEAD_LETTERED, 4)
    assert (letter.attempts, letter.error_code, letter.fetch_run_id) == (4, "timeout", run.id)
    assert runtime.consecutive_failures == 0
    assert runtime.next_due_at == now + timedelta(seconds=runtime.interval_seconds)


@pytest.mark.parametrize("code", ["selector_drift", "blocked_private_address"])
def test_drift_and_blocked_targets_pause_the_source(
    db_session: Session, fetcher: SafeFetcher, code: str
) -> None:
    source = collectable(db_session)
    error = CollectorError(code, "structure changed", retryable=False)

    run = collect(db_session, source, StubCollector(error), fetcher)

    assert run.outcome is FetchOutcome.DEAD_LETTERED
    assert source.status is SourceStatus.PAUSED
    assert source.paused_reason is not None and source.paused_reason.startswith(code)
    assert count(db_session, DeadLetter) == 1


def test_final_http_error_dead_letters_without_pausing(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    error = CollectorError("http_404", "HTTP 404", retryable=False, status_code=404)

    run = collect(db_session, source, StubCollector(error), fetcher)

    assert (run.outcome, run.http_status) == (FetchOutcome.DEAD_LETTERED, 404)
    assert source.status is SourceStatus.CANDIDATE


def test_local_rate_limit_defers_by_a_minute(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(db_session, config={"rate_per_minute": 10})
    stub = StubCollector()
    budget = Budget(allow=False)

    run = collect(db_session, source, stub, fetcher, budget=budget)

    assert (run.outcome, run.error_code) == (FetchOutcome.SKIPPED, "local_rate_limit")
    assert runtime_of(db_session, source).next_due_at == NOW + timedelta(seconds=60)
    assert budget.calls == [("www.example.com", 10)]
    assert stub.contexts == []


def test_unvalidated_sources_are_not_collected(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(db_session, validation_stage=ValidationStage.V2)
    stub = StubCollector()

    run = collect(db_session, source, stub, fetcher)

    assert (run.outcome, run.error_code) == (FetchOutcome.SKIPPED, "not_collectable")
    assert stub.contexts == []


def test_active_source_items_are_not_canary(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(
        db_session, validation_stage=ValidationStage.V6, status=SourceStatus.ACTIVE
    )

    run = collect(db_session, source, StubCollector(ok(raw(1))), fetcher)

    assert run.canary is False
    assert db_session.scalars(select(Item)).one().canary is False


def test_missing_credentials_pause_the_source(
    db_session: Session, fetcher: SafeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE_SECRET_GITHUB_TOKEN", raising=False)
    source = collectable(db_session, config={"auth": {"secret": "GITHUB_TOKEN"}})
    stub = StubCollector()

    run = collect(db_session, source, stub, fetcher)

    assert (run.outcome, run.error_code) == (FetchOutcome.DEAD_LETTERED, "config_error")
    assert source.status is SourceStatus.PAUSED
    assert stub.contexts == []


def test_collectors_receive_preset_config_and_credentials(
    db_session: Session, fetcher: SafeFetcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_SECRET_GITHUB_TOKEN", "t0k")
    source = collectable(
        db_session, config={"preset": "github_search", "auth": {"secret": "GITHUB_TOKEN"}}
    )
    stub = StubCollector(ok(raw(1)))

    collect(db_session, source, stub, fetcher)

    assert stub.contexts[0].config["list_path"] == "items"
    assert stub.contexts[0].headers == {"Authorization": "Bearer t0k"}


def test_repeated_dead_letter_merges_and_pauses(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(db_session)
    forbidden = CollectorError("http_403", "HTTP 403", retryable=False, status_code=403)

    collect(db_session, source, StubCollector(forbidden), fetcher)
    assert source.status is SourceStatus.CANDIDATE
    collect(db_session, source, StubCollector(forbidden), fetcher, now=NOW + timedelta(hours=6))

    letters = list(db_session.scalars(select(DeadLetter)))
    assert len(letters) == 1 and letters[0].attempts == 2
    assert source.status is SourceStatus.PAUSED
    assert source.paused_reason is not None and source.paused_reason.startswith("repeated http_403")


def test_wrong_content_type_pauses_only_on_the_second_strike(
    db_session: Session, fetcher: SafeFetcher
) -> None:
    source = collectable(db_session)
    html = CollectorError("blocked_mime", "unexpected content type 'text/html'", retryable=False)

    collect(db_session, source, StubCollector(html), fetcher)
    first = source.status
    collect(db_session, source, StubCollector(html), fetcher, now=NOW + timedelta(hours=6))

    assert first is SourceStatus.CANDIDATE and source.status is SourceStatus.PAUSED


def test_server_requested_wait_delays_the_retry(db_session: Session, fetcher: SafeFetcher) -> None:
    source = collectable(db_session)
    throttled = CollectorError("rate_limited", "throttle", retryable=True, retry_after=10830)

    collect(db_session, source, StubCollector(throttled), fetcher)

    assert runtime_of(db_session, source).next_due_at == NOW + timedelta(seconds=10830)
