import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from news_insight.public import maturity
from news_insight.taxonomy.seed import backfill_labels, seed_taxonomy
from tests.public.seed import Spec, seed_corpus

pytestmark = pytest.mark.db

OLED = ("display_av__display_panel",)
AGENTS = ("ai__ai_agents",)
EXTRA = (
    tuple(Spec(f"OLED launch {n}", "verge", 2 + n, "display_av", OLED, "launch") for n in range(6))
    + tuple(
        Spec(f"OLED market {n}", "verge", 30 + n, "display_av", OLED, "market") for n in range(3)
    )
    + tuple(Spec(f"Agent paper {n}", "arxiv", 5 + n, "ai", AGENTS, "research") for n in range(9))
)


def test_areas_take_the_stage_of_their_signal_mix(
    public_client: TestClient,
    public_headers: dict[str, str],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_corpus(db_session, EXTRA)
    seed_taxonomy(db_session)
    backfill_labels(db_session)
    monkeypatch.setattr(maturity, "MIN_CARDS", 5)
    body = public_client.get("/api/public/maturity", headers=public_headers).json()
    areas = {a["key"]: a for a in body["areas"]}
    panel, agents = areas["display_av__display_panel"], areas["ai__ai_agents"]
    assert panel["stage"] == "product" and 3.0 <= panel["index"] < 4.0
    assert agents["stage"] == "research" and agents["index"] < 2.0
    assert body["areas"][0]["index"] <= body["areas"][-1]["index"]  # earliest first
    assert {f["key"] for f in body["fields"]} >= {"ai", "display_av"}
    only = public_client.get(
        "/api/public/maturity", params={"field": "ai"}, headers=public_headers
    ).json()
    assert {a["field_key"] for a in only["areas"]} == {"ai"}
    assert panel["history"] and panel["history"][-1]["count"] >= 1
