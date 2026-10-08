import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.taxonomy.seed import seed_taxonomy

pytestmark = pytest.mark.db


def test_public_schemes_hide_inactive_nodes(
    db_session: Session, public_client: TestClient, public_headers: dict[str, str]
) -> None:
    seed_taxonomy(db_session)
    from tests.taxonomy.test_schemes import node

    node(db_session, "signal_type", "ip").status = "deprecated"
    db_session.flush()

    body = public_client.get("/api/public/taxonomy/schemes", headers=public_headers).json()

    signals = next(s for s in body["schemes"] if s["key"] == "signal_type")
    assert "ip" not in {n["key"] for n in signals["nodes"]} and "aliases" not in signals["nodes"][0]
    assert public_client.get("/api/public/taxonomy", headers=public_headers).status_code == 200
