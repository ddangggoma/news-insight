from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.enums import SourceStatus, ValidationOutcome, ValidationStage
from news_insight.sources.ladder import LadderError
from news_insight.sources.service import (
    SourceNotFound,
    StageNotAutomated,
    climb,
    get_source,
    run_check,
    stage_counts,
)
from tests.factories import build_source
from tests.parsers.test_feed_probe import item, rss

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


@pytest.fixture
def feed_fetcher() -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml"},
            content=rss(item(1), item(2), item(3)),
        )

    return SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda host, port: ["93.184.216.34"],
        verify_peer=False,
    )


def test_climb_runs_v0_to_v3_for_healthy_feed(
    db_session: Session, feed_fetcher: SafeFetcher
) -> None:
    source = build_source()
    db_session.add(source)
    db_session.flush()

    events = climb(db_session, source, fetcher=feed_fetcher, now=NOW)

    assert [event.stage for event in events] == [
        ValidationStage.V0,
        ValidationStage.V1,
        ValidationStage.V2,
        ValidationStage.V3,
    ]
    assert all(event.outcome is ValidationOutcome.PASSED for event in events)
    assert source.validation_stage is ValidationStage.V3


def test_climb_stops_at_first_failure(db_session: Session, feed_fetcher: SafeFetcher) -> None:
    source = build_source(terms_url=None)
    db_session.add(source)
    db_session.flush()

    events = climb(db_session, source, fetcher=feed_fetcher, now=NOW)

    assert [(e.stage, e.outcome) for e in events] == [
        (ValidationStage.V0, ValidationOutcome.PASSED),
        (ValidationStage.V1, ValidationOutcome.FAILED),
    ]
    assert source.validation_stage is ValidationStage.V0


def test_v4_and_v5_are_not_automated_yet(db_session: Session, feed_fetcher: SafeFetcher) -> None:
    source = build_source(validation_stage=ValidationStage.V3)
    db_session.add(source)
    db_session.flush()

    with pytest.raises(StageNotAutomated, match="V4"):
        run_check(db_session, source, ValidationStage.V4, fetcher=feed_fetcher, now=NOW)


def test_out_of_order_check_is_rejected_before_any_network_call(db_session: Session) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched")

    fetcher = SafeFetcher(
        client=httpx.Client(transport=httpx.MockTransport(explode)),
        resolver=lambda host, port: ["93.184.216.34"],
        verify_peer=False,
    )
    source = build_source()
    db_session.add(source)
    db_session.flush()

    with pytest.raises(LadderError):
        run_check(db_session, source, ValidationStage.V2, fetcher=fetcher, now=NOW)


def test_v6_gate_activates_source_with_quota_room(
    db_session: Session, feed_fetcher: SafeFetcher
) -> None:
    source = build_source(validation_stage=ValidationStage.V5)
    db_session.add(source)
    db_session.flush()

    event = run_check(db_session, source, ValidationStage.V6, fetcher=feed_fetcher, now=NOW)

    assert event.outcome is ValidationOutcome.PASSED
    assert source.status is SourceStatus.ACTIVE


def test_get_source_and_stage_counts(db_session: Session) -> None:
    db_session.add_all(
        [build_source(key="a"), build_source(key="b", validation_stage=ValidationStage.V2)]
    )
    db_session.flush()

    assert get_source(db_session, "a").key == "a"
    with pytest.raises(SourceNotFound):
        get_source(db_session, "missing")
    counts = stage_counts(db_session)
    assert counts[ValidationStage.UNVERIFIED] == 1
    assert counts[ValidationStage.V2] == 1
