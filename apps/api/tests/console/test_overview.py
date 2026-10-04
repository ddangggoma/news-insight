from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun
from news_insight.config import Settings, get_settings
from news_insight.main import create_app
from news_insight.sources.enums import Region, SourceStatus, Track, ValidationStage
from tests.factories import build_source

pytestmark = pytest.mark.db


def test_requests_without_the_key_are_rejected(console_client: TestClient) -> None:
    assert console_client.get("/api/admin/overview").status_code == 401
    assert (
        console_client.get("/api/admin/overview", headers={"X-Console-Key": "nope"}).status_code
        == 401
    )


def test_console_is_disabled_without_a_configured_key() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, console_api_key="")

    response = TestClient(app).get("/api/admin/overview", headers={"X-Console-Key": "x"})

    assert response.status_code == 503


def test_overview_summarises_portfolio_and_health(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    active = build_source(
        key="active-kr",
        region=Region.KR,
        language="ko",
        validation_stage=ValidationStage.V6,
        status=SourceStatus.ACTIVE,
    )
    paused = build_source(key="paused", status=SourceStatus.PAUSED)
    db_session.add_all([active, paused])
    db_session.flush()
    now = datetime.now(UTC)
    db_session.add_all(
        [
            FetchRun(
                source_id=active.id,
                started_at=now - timedelta(hours=1),
                outcome=FetchOutcome.SUCCESS,
                items_new=7,
            ),
            FetchRun(
                source_id=active.id,
                started_at=now - timedelta(hours=2),
                outcome=FetchOutcome.FAILED,
            ),
            FetchRun(
                source_id=active.id,
                started_at=now - timedelta(days=3),
                outcome=FetchOutcome.SUCCESS,
                items_new=99,
            ),
            DeadLetter(source_id=paused.id, error_code="timeout", error_message="t", attempts=4),
        ]
    )
    db_session.flush()

    body = console_client.get("/api/admin/overview", headers=headers).json()

    news = next(track for track in body["tracks"] if track["track"] == Track.NEWS.value)
    kr = next(region for region in body["regions"] if region["region"] == "kr")
    assert (news["total"], news["active"], news["target"]) == (2, 1, 100)
    assert (kr["total"], kr["active"], kr["capacity"]) == (1, 1, 65)
    assert body["health"] == {
        "window_hours": 24,
        "runs": 2,
        "success": 1,
        "not_modified": 0,
        "failed": 1,
        "dead_lettered": 0,
        "skipped": 0,
        "items_new": 7,
        "paused_sources": 1,
        "open_dead_letters": 1,
    }
