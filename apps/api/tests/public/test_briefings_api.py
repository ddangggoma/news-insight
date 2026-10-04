import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from news_insight.briefing.models import Briefing, BriefingStatus
from news_insight.briefing.service import publish
from news_insight.cards.models import ItemCard
from tests.briefing.test_publish import DAY, FREEZE_AT, RULES, FakeClaude, seed

pytestmark = pytest.mark.db


def published(db_session: Session) -> Briefing:
    seed(db_session)
    db_session.execute(update(ItemCard).values(field="ai", impact="opportunity"))
    briefing = publish(
        db_session,
        briefing_date=DAY,
        now=FREEZE_AT,
        client=FakeClaude(),
        model="opus",
        rules=RULES,
        with_strategy=False,
    )
    assert briefing.status is BriefingStatus.PUBLISHED
    return briefing


def test_briefings_need_the_public_key(db_session: Session, public_client: TestClient) -> None:
    published(db_session)

    assert public_client.get("/api/public/briefings/latest").status_code == 401


def test_latest_briefing_by_track(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    assert (
        public_client.get("/api/public/briefings/latest", headers=public_headers).status_code == 404
    )
    published(db_session)

    body = public_client.get("/api/public/briefings/latest", headers=public_headers).json()

    assert body["briefing_date"] == str(DAY) and body["headline"] == "헤드라인"
    assert [s["track"] for s in body["sections"]] == ["news", "research_ip", "oss", "community"]
    item = body["sections"][0]["items"][0]
    assert item["field"] == "ai" and "source_key" not in item and "engine" not in item
    assert body["gates_passed"] == body["gates_total"] > 0
    assert {ref["id"] for ref in body["refs"]} >= set(body["insights"][0]["item_ids"])
    assert body["previous_date"] is None and body["next_date"] is None
    dated = public_client.get(f"/api/public/briefings/{DAY}", headers=public_headers)
    missing = public_client.get("/api/public/briefings/2020-01-01", headers=public_headers)
    assert dated.status_code == 200 and missing.status_code == 404


def test_blocked_briefings_stay_private(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    briefing = published(db_session)
    briefing.status = BriefingStatus.BLOCKED
    db_session.flush()

    assert (
        public_client.get("/api/public/briefings/latest", headers=public_headers).status_code == 404
    )
    listed = public_client.get("/api/public/briefings", headers=public_headers).json()
    assert listed["total"] == 0


def test_archive_lists_headlines(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    published(db_session)

    listed = public_client.get("/api/public/briefings", headers=public_headers).json()

    assert listed["total"] == 1
    assert listed["items"][0]["headline"] == "헤드라인" and listed["items"][0]["items"] == 8
