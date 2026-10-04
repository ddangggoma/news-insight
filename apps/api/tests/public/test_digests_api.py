from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.digest.models import Digest, DigestStatus
from tests.public.seed import NOW

pytestmark = pytest.mark.db


def add_digest(session: Session, day: date, headline: str) -> None:
    session.add(
        Digest(
            digest_date=day,
            version=1,
            status=DigestStatus.PUBLISHED,
            model="opus",
            generated_at=NOW,
            window_start=NOW - timedelta(days=1),
            window_end=NOW,
            item_count=12,
            input_hash="x" * 64,
            content={"headline": headline, "overview": "개요", "tracks": [], "insights": []},
            cost_usd=1.25,
            error=None,
        )
    )
    session.flush()


def test_public_digests_hide_cost_and_model(
    public_client: TestClient, public_headers: dict[str, str], db_session: Session
) -> None:
    add_digest(db_session, date(2026, 10, 3), "어제")
    add_digest(db_session, date(2026, 10, 4), "오늘")
    latest = public_client.get("/api/public/digests/latest", headers=public_headers).json()
    assert latest["content"]["headline"] == "오늘"
    assert latest["item_count"] == 12
    assert not {"cost_usd", "model", "error"} & latest.keys()
    one = public_client.get("/api/public/digests/2026-10-03", headers=public_headers).json()
    assert one["content"]["headline"] == "어제"
    archive = public_client.get("/api/public/digests", headers=public_headers).json()
    assert [row["headline"] for row in archive["items"]] == ["오늘", "어제"]


def test_missing_digests_are_404(public_client: TestClient, public_headers: dict[str, str]) -> None:
    assert (
        public_client.get("/api/public/digests/latest", headers=public_headers).status_code == 404
    )
    missing = public_client.get("/api/public/digests/2026-01-01", headers=public_headers)
    assert missing.status_code == 404
