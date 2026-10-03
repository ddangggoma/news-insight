from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.collect.models import DeadLetter, FetchOutcome, FetchRun, SourceRuntime
from news_insight.sources.enums import ValidationStage
from tests.factories import build_source

pytestmark = pytest.mark.db
NOW = datetime(2026, 10, 3, tzinfo=UTC)


def test_runs_are_listed_newest_first_and_filtered(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    source = build_source(validation_stage=ValidationStage.V3)
    db_session.add(source)
    db_session.flush()
    db_session.add_all(
        [
            FetchRun(
                source_id=source.id,
                started_at=NOW - timedelta(hours=2),
                outcome=FetchOutcome.SUCCESS,
            ),
            FetchRun(
                source_id=source.id,
                started_at=NOW,
                outcome=FetchOutcome.FAILED,
                error_code="timeout",
            ),
        ]
    )
    db_session.flush()

    runs = console_client.get("/api/admin/runs", headers=headers).json()
    failed = console_client.get("/api/admin/runs?outcome=failed", headers=headers).json()

    assert [run["outcome"] for run in runs["items"]] == ["failed", "success"]
    assert runs["items"][0]["source_key"] == "example-news"
    assert [run["error_code"] for run in failed["items"]] == ["timeout"]


def test_dead_letters_can_be_retried_or_dismissed(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    source = build_source(validation_stage=ValidationStage.V3)
    db_session.add(source)
    db_session.flush()
    db_session.add(
        SourceRuntime(
            source_id=source.id, next_due_at=NOW + timedelta(hours=1), interval_seconds=900
        )
    )
    first = DeadLetter(source_id=source.id, error_code="timeout", error_message="t", attempts=4)
    second = DeadLetter(source_id=source.id, error_code="http_404", error_message="nf", attempts=1)
    db_session.add_all([first, second])
    db_session.flush()

    open_letters = console_client.get("/api/admin/dead-letters", headers=headers).json()
    retried = console_client.post(
        f"/api/admin/dead-letters/{first.id}/retry", headers=headers
    ).json()
    dismissed = console_client.post(
        f"/api/admin/dead-letters/{second.id}/dismiss", headers=headers
    ).json()
    again = console_client.post(f"/api/admin/dead-letters/{second.id}/dismiss", headers=headers)
    resolved = console_client.get("/api/admin/dead-letters?state=resolved", headers=headers).json()

    assert open_letters["total"] == 2
    assert (retried["resolution"], dismissed["resolution"]) == ("retried", "dismissed")
    assert again.status_code == 409
    assert resolved["total"] == 2
