from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingFreeze, BriefingStatus
from news_insight.cards.models import CardRun
from news_insight.collect.models import FetchOutcome, FetchRun
from news_insight.config import Settings
from news_insight.ops import service
from news_insight.ops.checks import (
    check_accounts,
    check_cards,
    check_collection,
    check_publication,
    check_queue,
    run_checks,
)
from news_insight.ops.models import Severity
from tests.factories import build_source

pytestmark = pytest.mark.db
DAY = date(2026, 10, 5)
AT_0450 = datetime(2026, 10, 4, 19, 50, tzinfo=UTC)  # 04:50 KST on DAY
AT_0530 = datetime(2026, 10, 4, 20, 30, tzinfo=UTC)  # 05:30 KST


def keys(findings: list[Any]) -> set[str]:
    return {f.key for f in findings}


def freeze(db_session: Session) -> BriefingFreeze:
    row = BriefingFreeze(
        briefing_date=DAY, frozen_at=AT_0450, candidate_ids=[], taxonomy_revision="t", config={}
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_publication_sla(db_session: Session) -> None:
    assert check_publication(db_session, now=AT_0450 - timedelta(minutes=20)) == []
    assert keys(check_publication(db_session, now=AT_0530)) == {"freeze_missing", "publish_sla"}

    frozen = freeze(db_session)
    db_session.add(
        Briefing(
            briefing_date=DAY,
            version=1,
            status=BriefingStatus.BLOCKED,
            freeze_id=frozen.id,
            input_hash="h",
            shortlist=[],
            published_at=AT_0450,
            gates=[
                {
                    "name": "korean",
                    "label": "한국 출처 비중",
                    "value": 0.1,
                    "threshold": 0.15,
                    "passed": False,
                    "blocking": True,
                }
            ],
        )
    )
    db_session.flush()

    blocked = check_publication(db_session, now=AT_0530)
    assert keys(blocked) == {"publish_blocked"} and "한국 출처 비중" in blocked[0].detail


def test_collection_health(db_session: Session) -> None:
    now = AT_0530
    assert keys(check_collection(db_session, now=now)) == {"collection_stalled"}

    source = build_source()
    db_session.add(source)
    db_session.flush()
    for index in range(30):
        outcome = FetchOutcome.SUCCESS if index < 10 else FetchOutcome.FAILED
        db_session.add(
            FetchRun(source_id=source.id, started_at=now - timedelta(minutes=5), outcome=outcome)
        )
    db_session.flush()

    degraded = check_collection(db_session, now=now)
    assert keys(degraded) == {"collection_degraded"} and "33%" in degraded[0].title


def test_queue_and_cards(db_session: Session) -> None:
    assert keys(check_queue(None)) == {"redis_unreachable"}
    assert keys(check_queue(10)) == set() and keys(check_queue(900)) == {"queue_backlog"}
    db_session.add(CardRun(started_at=AT_0530 - timedelta(minutes=5), batches={}, quota={}))
    db_session.flush()
    assert check_cards(db_session, now=AT_0530) == []


def test_alert_episodes_open_update_and_resolve(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(
        service, "send_email", lambda settings, **kw: sent.append(kw["subject"]) or True
    )
    settings = Settings(_env_file=None, smtp_host="smtp.example")

    first = service.sync_alerts(
        db_session, run_checks(db_session, now=AT_0530, queue_length=0), now=AT_0530
    )
    assert service.notify(settings, first, now=AT_0530) is True
    again = service.sync_alerts(
        db_session,
        run_checks(db_session, now=AT_0530, queue_length=0),
        now=AT_0530 + timedelta(minutes=5),
    )
    assert service.notify(settings, again, now=AT_0530) is False

    assert {a.key for a in first.opened} >= {"publish_sla", "collection_stalled"}
    assert again.opened == [] and len(sent) == 1
    assert all(a.notified_at is not None for a in first.opened if a.severity is not Severity.INFO)

    freeze(db_session)
    later = service.sync_alerts(db_session, [], now=AT_0530 + timedelta(hours=1))
    assert {a.key for a in later.resolved} == {a.key for a in again.open}
    assert service.open_alerts(db_session) == []


def test_console_alerts_api(
    db_session: Session, console_client: TestClient, headers: dict[str, str]
) -> None:
    service.sync_alerts(db_session, check_queue(900), now=AT_0530)

    body = console_client.get("/api/admin/alerts", headers=headers).json()

    assert body[0]["key"] == "queue_backlog" and body[0]["resolved_at"] is None


def test_card_failure_rate_alert(db_session: Session) -> None:
    db_session.add(
        CardRun(
            started_at=AT_0530 - timedelta(minutes=5),
            ready=60,
            failed=40,
            batches={},
            quota={},
            note="preservation",
        )
    )
    db_session.flush()

    assert "cards_failing" in keys(check_cards(db_session, now=AT_0530))


def test_missing_admin_account_is_flagged(db_session: Session) -> None:
    from news_insight.auth.accounts import create_admin

    assert [f.key for f in check_accounts(db_session)] == ["no_admin"]
    create_admin(
        db_session, username="boss", password="plum-orbit-4417", name="관리자", now=AT_0530
    )
    assert check_accounts(db_session) == []
