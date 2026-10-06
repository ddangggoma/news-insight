import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.periodic import service
from tests.periodic.test_periodic import MONDAY, NOW, FakeClaude, daily

pytestmark = pytest.mark.db


def test_periodic_api(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    daily(db_session, 4)
    assert (
        public_client.get("/api/public/periodic/week/latest", headers=public_headers).status_code
        == 404
    )
    service.generate(
        db_session, kind="week", key="2026-W40", now=NOW, client=FakeClaude(), model="opus"
    )

    listed = public_client.get("/api/public/periodic", headers=public_headers).json()
    body = public_client.get("/api/public/periodic/week/2026-W40", headers=public_headers).json()

    assert listed[0]["key"] == "2026-W40" and listed[0]["label"] == "주간 브리핑"
    assert body["period_end"] == "2026-10-04" and len(body["daily"]) == 4
    assert {r["id"] for r in body["refs"]} >= set(body["content"]["trends"][0]["item_ids"])
    assert body["previous_key"] is None and body["next_key"] is None
    assert service.due(db_session, NOW) == [("month", "2026-09")]
    for path in ("/periodic/week/2026-W39", "/periodic/year/2026"):
        assert public_client.get(f"/api/public{path}", headers=public_headers).status_code == 404
    latest = public_client.get(f"/api/public/briefings/{MONDAY}", headers=public_headers).json()
    assert latest["periodic"][0]["key"] == "2026-W40"
