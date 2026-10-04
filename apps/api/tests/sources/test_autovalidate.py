from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.orm import Session

from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.autovalidate import SessionScope, auto_validate, due_candidates
from news_insight.sources.enums import SourceStatus, ValidationOutcome, ValidationStage
from news_insight.sources.models import SourceValidationEvent
from tests.factories import build_source
from tests.helpers import mock_fetcher
from tests.sources.test_auto_policy import FEED

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def fetcher() -> SafeFetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if "broken" in request.url.host:
            return httpx.Response(500)
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=FEED)

    return mock_fetcher(handler)


def scope_for(db_session: Session) -> SessionScope:
    @contextmanager
    def scope() -> Iterator[Session]:
        with db_session.begin_nested():
            yield db_session

    return scope


def test_due_candidates_skip_recent_failures_and_advanced_sources(db_session: Session) -> None:
    fresh = build_source(key="fresh", terms_url=None, storage_right=None)
    failed_recently = build_source(key="recent", terms_url=None)
    failed_long_ago = build_source(key="old", terms_url=None)
    at_v3 = build_source(key="v3", validation_stage=ValidationStage.V3)
    paused = build_source(key="paused", status=SourceStatus.PAUSED)
    db_session.add_all([fresh, failed_recently, failed_long_ago, at_v3, paused])
    db_session.flush()
    for source, age in (
        (failed_recently, timedelta(hours=1)),
        (failed_long_ago, timedelta(days=2)),
    ):
        db_session.add(
            SourceValidationEvent(
                source=source,
                stage=ValidationStage.V0,
                outcome=ValidationOutcome.FAILED,
                reasons=["x"],
                metrics={},
                created_at=NOW - age,
            )
        )
    db_session.flush()

    due = due_candidates(db_session, now=NOW, limit=10)

    assert set(due) == {fresh.id, failed_long_ago.id}


def test_auto_validate_climbs_to_v3_and_isolates_failures(db_session: Session) -> None:
    good = build_source(key="good", terms_url=None, storage_right=None)
    broken = build_source(
        key="broken",
        terms_url=None,
        endpoint_url="https://broken.example.com/feed.xml",
    )
    db_session.add_all([good, broken])
    db_session.flush()

    stats = auto_validate(scope_for(db_session), fetcher=fetcher(), now=NOW, limit=10)

    assert (stats.checked, stats.reached_v3, stats.errors) == (2, 1, 0)
    assert stats.failed == {"V2": 1}
    assert good.validation_stage is ValidationStage.V3
    assert broken.validation_stage is ValidationStage.V1
