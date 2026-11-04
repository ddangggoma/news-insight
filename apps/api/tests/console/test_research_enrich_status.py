"""GET /api/admin/research/enrich-status: the dashboard's 보강 진행률 line (plan 19 §5)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.content.models import Item
from news_insight.research.models import EnrichStatus, ResearchMeta
from news_insight.sources.enums import Track
from tests.documents import document, source

pytestmark = pytest.mark.db


def asked(session: Session, item: Item, status: EnrichStatus, at: datetime) -> None:
    session.add(ResearchMeta(item_id=item.id, doi="10.1/x", status=status, enriched_at=at))
    session.flush()


def test_enrich_status_counts_papers_and_the_last_run(
    console_client: TestClient, headers: dict[str, str], db_session: Session
) -> None:
    papers = source(db_session, "arxiv")
    now = datetime.now(UTC)
    found = document(db_session, papers, "found", refs=(("arxiv", "2610.00001"),))
    missing = document(db_session, papers, "missing", refs=(("doi", "10.1/missing"),))
    document(db_session, papers, "waiting", refs=(("doi", "10.1/waiting"),))
    document(db_session, papers, "no-ref")  # nothing to look up: not counted
    news = source(db_session, "verge", category="independent_media", track=Track.NEWS)
    document(db_session, news, "cites", refs=(("doi", "10.1/waiting"),))  # not a paper
    asked(db_session, found, EnrichStatus.OK, now - timedelta(hours=2))
    asked(db_session, missing, EnrichStatus.NOT_FOUND, now - timedelta(days=3))

    body = console_client.get("/api/admin/research/enrich-status", headers=headers).json()

    assert body["eligible"] == 3
    assert (body["asked"], body["ok"], body["not_found"], body["error"]) == (2, 1, 1, 0)
    assert body["enriched_share"] == pytest.approx(1 / 3, abs=0.001)
    assert body["asked_24h"] == 1
    last = datetime.fromisoformat(body["last_run_at"])
    assert abs((last - (now - timedelta(hours=2))).total_seconds()) < 1
    assert body["last_ok_at"] == body["last_run_at"]


def test_enrich_status_before_any_run(console_client: TestClient, headers: dict[str, str]) -> None:
    body = console_client.get("/api/admin/research/enrich-status", headers=headers).json()

    assert body["asked"] == 0 and body["last_run_at"] is None and body["enriched_share"] is None
